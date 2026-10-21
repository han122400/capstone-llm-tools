import itertools
import json

import pytest

from app.core import CONFIGS, POLICY_VERSION, calculate_metrics, combine_results, component_dependencies, input_hash, model_input


def test_selected_ensembles_resolve_three_unique_components():
    assert set(CONFIGS) == {"foundation_sec", "qwen", "jev", "foundation_sec_jev", "qwen_jev"}
    assert component_dependencies(["foundation_sec_jev", "qwen_jev", "jev"]) == ["foundation_sec", "qwen", "jev"]
    with pytest.raises(ValueError):
        component_dependencies(["unknown"])


@pytest.mark.parametrize("a,b,expected", [
    ("NORMAL", "NORMAL", "NORMAL"), ("INJECTION", "INJECTION", "INJECTION"),
    ("NORMAL", "INJECTION", "REVIEW"), ("INJECTION", "NORMAL", "REVIEW"),
    ("NORMAL", "REVIEW", "REVIEW"), ("REVIEW", "NORMAL", "REVIEW"),
    ("INJECTION", "REVIEW", "REVIEW"), ("REVIEW", "INJECTION", "REVIEW"),
    ("REVIEW", "REVIEW", "REVIEW"),
])
def test_combination_agreement_or_review(a, b, expected):
    assert combine_results({"status": "SUCCESS", "decision": a}, {"status": "SUCCESS", "decision": b}) == {
        "status": "SUCCESS", "decision": expected, "policy_version": POLICY_VERSION,
    }


@pytest.mark.parametrize("status", ["ERROR", "CANCELLED", "SKIPPED", "PENDING", "RUNNING"])
def test_incomplete_component_never_gets_decision(status):
    for first, second in [(status, "SUCCESS"), ("SUCCESS", status)]:
        result = combine_results({"status": first, "decision": "NORMAL"}, {"status": second, "decision": "NORMAL"})
        assert result["status"] == status
        assert result["decision"] is None


def test_error_overrides_review_and_invalid_success_is_error():
    assert combine_results({"status": "ERROR"}, {"status": "SUCCESS", "decision": "REVIEW"})["status"] == "ERROR"
    assert combine_results({"status": "SUCCESS", "decision": None}, {"status": "SUCCESS", "decision": "NORMAL"})["status"] == "ERROR"


def test_model_input_excludes_answers_metadata_and_normalizes_linebreaks():
    sample = {"subject": "보고", "body": "first\r\nsecond\rthird", "label": "INJECTION", "sample_id": "attack-secret", "type": "ignore", "notes": "ground truth"}
    text = model_input(sample)
    assert json.loads(text) == {"subject": "보고", "body": "first\nsecond\nthird"}
    assert "INJECTION" not in text and "attack-secret" not in text
    assert input_hash(text) == input_hash(model_input({"subject": "보고", "body": "first\nsecond\nthird"}))


def test_required_metric_fixture_preserves_all_denominators():
    samples = [{"sample_id": str(i), "label": "NORMAL" if i < 4 else "INJECTION"} for i in range(8)]
    decisions = ["NORMAL", "NORMAL", "INJECTION", "REVIEW", "INJECTION", "INJECTION", "NORMAL", None]
    results = [{"sample_id": str(i), "status": "ERROR" if i == 7 else "SUCCESS", "decision": d, "latency_ms": i * 10} for i, d in enumerate(decisions)]
    output = calculate_metrics(samples, results)
    assert output["N"] == 8
    for key, numerator, denominator in [
        ("automatic_rate", 6, 8), ("correct_rate", 4, 8), ("injection_detection_rate", 2, 4),
        ("miss_rate", 1, 4), ("false_positive_rate", 1, 4), ("review_rate", 1, 8),
        ("error_rate", 1, 8), ("precision", 2, 3), ("recall", 2, 3), ("f1", 4, 6),
    ]:
        metric = output["metrics"][key]
        assert metric["numerator"] == numerator and metric["denominator"] == denominator
        assert metric["value"] == pytest.approx(numerator / denominator)
        assert metric["description"]
    assert output["confusion"]["NORMAL"] == {"NORMAL": 2, "INJECTION": 1, "REVIEW": 1}
    assert output["confusion"]["INJECTION"] == {"NORMAL": 1, "INJECTION": 2, "REVIEW": 0}
    assert output["latency"]["success"]["count"] == 7
    assert output["latency"]["error"]["mean_ms"] == 70


@pytest.mark.parametrize("status,decision", [("SUCCESS", "REVIEW"), ("ERROR", None), ("CANCELLED", None), ("RUNNING", None)])
def test_metrics_all_review_failure_or_partial_do_not_fake_accuracy(status, decision):
    samples = [{"sample_id": "one", "label": "INJECTION"}]
    result = calculate_metrics(samples, [{"sample_id": "one", "status": status, "decision": decision}])
    assert result["metrics"]["automatic_rate"]["value"] == 0
    assert result["metrics"]["precision"]["value"] is None
    assert result["metrics"]["false_positive_rate"]["value"] is None
    assert result["counts"][status] == 1


def test_empty_and_missing_results_keep_snapshot_denominator():
    assert all(v["value"] is None for v in calculate_metrics([], [])["metrics"].values())
    result = calculate_metrics([{"sample_id": "one", "label": "NORMAL"}], [])
    assert result["N"] == 1 and result["counts"]["PENDING"] == 1
    assert result["metrics"]["automatic_rate"]["value"] == 0
