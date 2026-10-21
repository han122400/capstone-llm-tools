"""Pure evaluation contracts. Inputs and model outputs are untrusted data."""

import hashlib
import json
import math
import statistics

from .prompts import PROMPT_VERSION, SYSTEM_PROMPT

PREPROCESS_VERSION = "subject-body-lf-v1"
POLICY_VERSION = "unanimous-or-review-v1"
DECISIONS = {"NORMAL", "INJECTION", "REVIEW"}
STATUSES = ("PENDING", "RUNNING", "SUCCESS", "ERROR", "CANCELLED", "SKIPPED")
INPUT_BUDGET_VERSION = "utf8-reserve-v2"
TEMPLATE_RESERVE = 512
MAX_INPUT_BYTES = min(3000, 4096 - len(SYSTEM_PROMPT.encode("utf-8")) - 64 - TEMPLATE_RESERVE - 1)


def common_input_limit(settings):
    return input_budget(settings)["input_limit_bytes"]


def input_budget(settings):
    context = int(settings.get("context_length", 4096))
    output = int(settings.get("max_output_tokens", 64))
    prompt_bytes = len(SYSTEM_PROMPT.encode("utf-8"))
    # The adapter rejects totals >= num_ctx; reserve one additional token here.
    remaining = context - prompt_bytes - output - TEMPLATE_RESERVE - 1
    return {"version": INPUT_BUDGET_VERSION, "context_length": context,
            "system_prompt_bytes": prompt_bytes, "output_reserved_tokens": output,
            "template_reserve_tokens": TEMPLATE_RESERVE, "boundary_reserve_tokens": 1,
            "input_limit_bytes": max(0, min(3000, remaining)), "input_cap_bytes": 3000,
            "valid": remaining > 0, "exact_tokenizer_verified": False,
            "method": "UTF-8 bytes as conservative text token bound; template reserve assumed, model system/messages checked separately; no truncation"}


def validate_input_budget(settings):
    budget = input_budget(settings)
    if not budget['valid']:
        raise ValueError('컨텍스트에 입력 공간이 없습니다. 컨텍스트 길이를 늘리거나 출력 토큰 제한을 낮추세요. 시스템 프롬프트·출력·템플릿 여유를 함께 예약합니다.')
    return budget

CONFIGS = {
    "foundation_sec": {"id": "foundation_sec", "name": "Foundation-Sec", "kind": "Local", "components": ["foundation_sec"]},
    "qwen": {"id": "qwen", "name": "Qwen", "kind": "Local", "components": ["qwen"]},
    "jev": {"id": "jev", "name": "Jev", "kind": "API", "components": ["jev"]},
    "foundation_sec_jev": {"id": "foundation_sec_jev", "name": "Foundation-Sec + Jev", "kind": "Ensemble", "components": ["foundation_sec", "jev"]},
    "qwen_jev": {"id": "qwen_jev", "name": "Qwen + Jev", "kind": "Ensemble", "components": ["qwen", "jev"]},
}

# Historical IDs keep their original independent-vote meaning permanently.
CASCADE_CONFIGS = {
    f'{local}_then_jev': {'id':f'{local}_then_jev','name':f'{name} → Jev','kind':'Cascade','components':[local,'jev']}
    for local,name in [('foundation_sec','Foundation-Sec'),('qwen','Qwen')]
}
ACTIVE_CONFIGS = {**{k:v for k,v in CONFIGS.items() if k in ('foundation_sec','qwen','jev')}, **CASCADE_CONFIGS}
ALL_CONFIGS = {**CONFIGS, **CASCADE_CONFIGS}
LEGACY_CONFIG_IDS = {'foundation_sec_jev','qwen_jev'}


def config_definitions(identifiers):
    return [{**ALL_CONFIGS[k], 'name': ALL_CONFIGS[k]['name'] + (' · 기존 독립 결합' if k in LEGACY_CONFIG_IDS else '')} for k in identifiers if k in ALL_CONFIGS]


def component_dependencies(selected):
    unknown = set(selected) - set(ALL_CONFIGS)
    if unknown:
        raise ValueError(f"Unknown configurations: {sorted(unknown)}")
    needed = {c for identifier in selected for c in ALL_CONFIGS[identifier]["components"]}
    return [c for c in ("foundation_sec", "qwen", "jev") if c in needed]


def model_input(sample):
    from .email_input import analysis_input
    return analysis_input(sample)


def input_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def combine_results(a, b):
    statuses = [a.get("status", "PENDING"), b.get("status", "PENDING")]
    status = "SUCCESS"
    # Error takes precedence; unfinished and cancellation remain distinct.
    for candidate in ("ERROR", "CANCELLED", "RUNNING", "PENDING", "SKIPPED"):
        if candidate in statuses:
            status = candidate
            break
    if any(s not in STATUSES for s in statuses):
        status = "ERROR"
    decision = None
    if status == "SUCCESS":
        first, second = a.get("decision"), b.get("decision")
        if first not in DECISIONS or second not in DECISIONS:
            status = "ERROR"
        else:
            decision = first if first == second and first != "REVIEW" else "REVIEW"
    return {"status": status, "decision": decision, "policy_version": POLICY_VERSION}


def _latency_stats(values):
    if not values:
        return {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None}
    values = sorted(values)
    position = (len(values) - 1) * 0.95
    lo, hi = math.floor(position), math.ceil(position)
    p95 = values[lo] + (values[hi] - values[lo]) * (position - lo)
    return {"count": len(values), "mean_ms": statistics.mean(values), "median_ms": statistics.median(values), "p95_ms": p95, "max_ms": max(values)}


def calculate_metrics(samples, results):
    n = len(samples)
    counts = {s: 0 for s in STATUSES}
    confusion = {label: {decision: 0 for decision in ("NORMAL", "INJECTION", "REVIEW")} for label in ("NORMAL", "INJECTION")}
    by_sample = {str(r.get("sample_id")): r for r in results}
    actual = {label: sum(s.get("label") == label for s in samples) for label in confusion}
    injection_errors = 0
    latency = {"success": [], "error": []}
    for sample in samples:
        result = by_sample.get(str(sample.get("sample_id")), {"status": "PENDING"})
        status = result.get("status", "PENDING")
        decision = result.get("decision")
        if status not in STATUSES or (status == "SUCCESS" and decision not in DECISIONS):
            status = "ERROR"
        counts[status] += 1
        label = sample.get("label")
        if status == "SUCCESS" and label in confusion:
            confusion[label][decision] += 1
        if status == "ERROR" and label == "INJECTION":
            injection_errors += 1
        elapsed = result.get("latency_ms")
        if status in ("SUCCESS", "ERROR") and isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0:
            latency[status.lower()].append(elapsed)
    tp, fp = confusion["INJECTION"]["INJECTION"], confusion["NORMAL"]["INJECTION"]
    fn, tn = confusion["INJECTION"]["NORMAL"], confusion["NORMAL"]["NORMAL"]
    review = confusion["NORMAL"]["REVIEW"] + confusion["INJECTION"]["REVIEW"]
    definitions = {
        "automatic_rate": (tp + fp + fn + tn, n, "SUCCESS의 NORMAL 또는 INJECTION / 전체 스냅샷 N"),
        "review_rate": (review, n, "SUCCESS의 REVIEW / 전체 스냅샷 N"),
        "correct_rate": (tp + tn, n, "정답과 일치한 자동 판정 / 전체 스냅샷 N"),
        "injection_detection_rate": (tp, actual["INJECTION"], "실제 INJECTION → INJECTION / 실제 INJECTION 전체 (REVIEW·실패 포함)"),
        "miss_rate": (fn, actual["INJECTION"], "실제 INJECTION → NORMAL / 실제 INJECTION 전체; 1−탐지율과 다름"),
        "false_positive_rate": (fp, actual["NORMAL"], "실제 NORMAL → INJECTION / 실제 NORMAL 전체"),
        "error_rate": (counts["ERROR"], n, "기술적 ERROR / 전체 스냅샷 N"),
        "injection_review_rate": (confusion["INJECTION"]["REVIEW"], actual["INJECTION"], "실제 INJECTION → REVIEW / 실제 INJECTION 전체"),
        "injection_error_rate": (injection_errors, actual["INJECTION"], "실제 INJECTION → ERROR / 실제 INJECTION 전체"),
        "precision": (tp, tp + fp, "자동 판정 집합 Precision = TP / (TP+FP); 자동 판정률과 함께 해석"),
        "recall": (tp, tp + fn, "자동 판정 집합 Recall = TP / (TP+FN); REVIEW·실패 제외로 전체 인젝션 탐지율과 분모가 다름"),
        "f1": (2 * tp, 2 * tp + fp + fn, "자동 판정 집합 F1 = 2TP / (2TP+FP+FN); REVIEW·실패 제외"),
    }
    metrics = {key: {"value": numerator / denominator if denominator else None, "numerator": numerator, "denominator": denominator, "description": description} for key, (numerator, denominator, description) in definitions.items()}
    return {"N": n, "counts": counts, "class_counts": actual, "confusion": confusion, "metrics": metrics, "latency": {key: _latency_stats(value) for key, value in latency.items()}, "partial": any(counts[s] for s in ("PENDING", "RUNNING", "CANCELLED", "SKIPPED")), "p95_note": "P95는 선형 보간값이며 소표본에서 안정적인 대표 성능이 아닙니다."}
