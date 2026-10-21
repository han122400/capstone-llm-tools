"""Integration invariants through the real SQLite store and evaluation scheduler.

All inference is injected. These tests never contact Ollama or a paid provider.
"""
import asyncio
import json

import pytest

from app.core import CONFIGS, input_hash, model_input
from app.engine import Engine
from app.store import Store


@pytest.fixture(autouse=True)
def isolate_host_resource_sampling(monkeypatch):
    # ResourceMonitor has its own tests. Integration tests exercise the queue
    # and persistence without enumerating unrelated Windows host processes.
    class Monitor:
        def start(self):
            return self

        def stop(self):
            return {"method": "injected-test-monitor", "backend_rss_peak_bytes": None}

    monkeypatch.setattr("app.telemetry.ResourceMonitor", Monitor)


def email(identifier="sample-1", label="NORMAL"):
    return {
        "sample_id": identifier,
        "subject": "검토 요청",
        "body": "본문 첫 줄\r\n본문 둘째 줄",
        "label": label,
        "language": "ko",
        "category": "SECRET_CATEGORY_NOT_FOR_MODEL",
        "synthetic": True,
        "notes": "SECRET_GROUND_TRUTH_NOTE",
        "template_family": "SECRET_ATTACK_TEMPLATE",
    }


def fake_factory(events, decide=None, on_predict=None):
    """Record lifecycle and deliberately unrealistic reported durations."""
    def factory(config_id, *args, **kwargs):
        class Adapter:
            async def prepare(self):
                events.append(("prepare", config_id))
                return {"ready": True, "status": "SUCCESS", "model": config_id}

            async def release(self):
                events.append(("release", config_id))
                return {"ready": True, "status": "SUCCESS"}

            async def predict(self, text):
                events.append(("predict", config_id, text))
                if on_predict:
                    on_predict(config_id, text)
                status, decision = decide(config_id, text) if decide else ("SUCCESS", "NORMAL")
                return {
                    "status": status,
                    "decision": decision,
                    "latency_ms": 1_000_000_000,
                    "cost": 0.1 if config_id == "jev" else None,
                    "provider": "test-provider",
                    "requested_model": config_id,
                    "actual_model": config_id + "-test-build",
                    "is_mock": True,
                    "attempts": [{"status": status, "latency_ms": 0}],
                    "raw_response": {"test": True},
                    "error": {"type": "TEST_FAILURE", "message": "test"} if status == "ERROR" else None,
                }
        return Adapter()
    return factory


def run_options(dataset_id, configs, mode="reuse"):
    return {"dataset_id": dataset_id, "configs": configs, "demo": True, "mode": mode}


def test_ensemble_only_reuses_same_jev_and_identical_leak_free_input(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        source = email("SECRET_SAMPLE_ID")
        dataset = store.save_dataset({"name": "test", "samples": [source]})
        events = []
        engine = Engine(store, factory=fake_factory(events))
        run = store.create_run(run_options(dataset["id"], ["foundation_sec_jev", "qwen_jev"]), {})
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)

        calls = [event for event in events if event[0] == "predict"]
        assert [event[1] for event in calls] == ["foundation_sec", "qwen", "jev"]
        expected_input = model_input(source)
        assert all(event[2] == expected_input for event in calls)
        assert json.loads(expected_input) == {"subject": source["subject"], "body": "본문 첫 줄\n본문 둘째 줄"}
        assert "SECRET_" not in expected_input

        components = {result["config_id"]: result for result in saved["results"] if result["config_id"] in ("foundation_sec", "qwen", "jev")}
        ensembles = [result for result in saved["results"] if result["config_id"].endswith("_jev")]
        assert len(saved["results"]) == 5 and len(ensembles) == 2
        assert all(result["input_hash"] == input_hash(expected_input) for result in saved["results"])
        assert all(components["jev"]["id"] in result["component_result_ids"] for result in ensembles)
        assert all(result["reused"] and result["latency_ms"] is None for result in ensembles)
        assert len({result["policy_version"] for result in ensembles}) == 1
        assert saved["totals"]["api_calls"] == 1
        assert saved["totals"]["cost_usd"] == pytest.approx(0.1)
        assert set(saved["metrics"]) == {"foundation_sec_jev", "qwen_jev"}
        assert all(metric["N"] == 1 for metric in saved["metrics"].values())

    asyncio.run(scenario())


def test_local_model_batches_release_before_switching(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email("one"), email("two")]})
        events = []
        engine = Engine(store, factory=fake_factory(events))
        run = store.create_run(run_options(dataset["id"], list(CONFIGS)), {})
        await engine.execute(run["id"], True)
        predictions = [event[1] for event in events if event[0] == "predict"]
        assert predictions == ["foundation_sec", "foundation_sec", "qwen", "qwen", "jev", "jev"]
        assert events.index(("release", "foundation_sec")) < events.index(("prepare", "qwen"))
        assert events.index(("release", "qwen")) > events.index(("prepare", "qwen"))

    asyncio.run(scenario())


def test_separate_experiments_do_not_reuse_results_and_keep_snapshot(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email()]})
        events = []
        engine = Engine(store, factory=fake_factory(events))
        first = store.create_run(run_options(dataset["id"], ["qwen_jev"]), {"temperature": 0})
        await engine.execute(first["id"], True)
        before = store.get_run(first["id"], True)
        replacement = email()
        replacement["body"] = "완전히 수정한 본문"
        store.save_dataset({"name": "updated", "samples": [replacement]}, dataset["id"])
        second = store.create_run(run_options(dataset["id"], ["qwen_jev"]), {"temperature": 0.5})
        await engine.execute(second["id"], True)
        after = store.get_run(first["id"], True)
        newer = store.get_run(second["id"], True)

        assert len([event for event in events if event[0] == "predict"]) == 4
        assert after["dataset_snapshot"] == before["dataset_snapshot"]
        assert after["results"] == before["results"]
        assert after["settings"]["temperature"] == 0
        assert newer["settings"]["temperature"] == 0.5
        assert after["dataset_snapshot"]["version"] == 1
        assert newer["dataset_snapshot"]["version"] == 2
        old_ids = {result["id"] for result in after["results"]}
        assert old_ids.isdisjoint(result["id"] for result in newer["results"])
        assert all(old_ids.isdisjoint(result.get("component_result_ids", [])) for result in newer["results"])

    asyncio.run(scenario())


def test_component_technical_error_propagates_without_fabricating_review(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email()]})
        decide = lambda config, _: ("ERROR", "NORMAL") if config == "jev" else ("SUCCESS", "NORMAL")
        engine = Engine(store, factory=fake_factory([], decide=decide))
        run = store.create_run(run_options(dataset["id"], list(CONFIGS)), {})
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)
        failed_configs = {"jev", "foundation_sec_jev", "qwen_jev"}
        for result in saved["results"]:
            if result["config_id"] in failed_configs:
                assert result["status"] == "ERROR" and result["decision"] is None
        for config in failed_configs:
            assert saved["metrics"][config]["N"] == 1
            assert saved["metrics"][config]["counts"]["ERROR"] == 1
            assert saved["metrics"][config]["metrics"]["review_rate"]["numerator"] == 0

    asyncio.run(scenario())


def test_cancellation_during_predict_is_not_overwritten_by_progress(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email("one"), email("two"), email("three")]})
        events = []
        run = store.create_run(run_options(dataset["id"], ["qwen_jev"]), {})
        engine = Engine(store, factory=fake_factory(events, on_predict=lambda *_: store.cancel(run["id"], True)))
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)
        assert saved["status"] == "CANCELLED"
        assert len([event for event in events if event[0] == "predict"]) == 1
        assert saved["metrics"]["qwen_jev"]["N"] == 3
        assert saved["metrics"]["qwen_jev"]["partial"] is True
        for result in saved["results"]:
            if result["status"] != "SUCCESS":
                assert result["decision"] is None
        assert not any(result["status"] == "RUNNING" for result in saved["results"])

    asyncio.run(scenario())


def test_cancellation_during_model_prepare_survives_event_persistence(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email()]})
        events = []
        run = store.create_run(run_options(dataset["id"], ["qwen_jev"]), {})
        base = fake_factory(events)

        def factory(config_id, *args, **kwargs):
            adapter = base(config_id, *args, **kwargs)
            if config_id == "qwen":
                async def cancel_while_loading():
                    events.append(("prepare", config_id))
                    store.cancel(run["id"], True)
                    return {"ready": True, "status": "SUCCESS"}
                adapter.prepare = cancel_while_loading
            return adapter

        engine = Engine(store, factory=factory)
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)
        assert saved["status"] == "CANCELLED"
        assert not any(event[0] == "predict" for event in events)
        assert ("release", "qwen") in events
        assert all(result["decision"] is None for result in saved["results"])

    asyncio.run(scenario())


def test_live_ensembles_have_own_calls_and_measured_end_to_end_latency(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email()]})
        events = []
        engine = Engine(store, factory=fake_factory(events))
        run = store.create_run(run_options(dataset["id"], ["foundation_sec_jev", "qwen_jev"], "live"), {})
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)
        calls = [event for event in events if event[0] == "predict"]
        assert len(calls) == 4 and sum(event[1] == "jev" for event in calls) == 2
        ensembles = [result for result in saved["results"] if result["config_id"].endswith("_jev")]
        assert len(ensembles) == 2
        for result in ensembles:
            assert result["reused"] is False
            # Components claim 1e9 ms. A fast injected call must not inherit the
            # sum or maximum of those stored times as a measured system delay.
            assert 0 <= result["latency_ms"] < 1_000_000
            assert len(result["component_result_ids"]) == 2
        assert set(ensembles[0]["component_result_ids"]).isdisjoint(ensembles[1]["component_result_ids"])
        assert saved["totals"]["api_calls"] == 2
        assert saved["totals"]["cost_usd"] == pytest.approx(0.2)

    asyncio.run(scenario())


def test_failed_prepare_attempts_cleanup_before_next_local_model(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email()]})
        events = []
        base = fake_factory(events)

        def factory(config_id, *args, **kwargs):
            adapter = base(config_id, *args, **kwargs)
            if config_id == "foundation_sec":
                async def prepare_failed_after_load():
                    events.append(("prepare", config_id))
                    return {"ready": False, "status": "ERROR", "error": {"type": "MODEL_LOAD_UNVERIFIED"}}
                adapter.prepare = prepare_failed_after_load
            return adapter

        engine = Engine(store, factory=factory)
        run = store.create_run(run_options(dataset["id"], ["foundation_sec", "qwen"]), {})
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)
        assert ("release", "foundation_sec") in events
        assert events.index(("release", "foundation_sec")) < events.index(("prepare", "qwen"))
        assert saved["metrics"]["foundation_sec"]["counts"]["ERROR"] == 1
        assert saved["metrics"]["qwen"]["counts"]["SUCCESS"] == 1

    asyncio.run(scenario())


def test_unverified_local_release_blocks_next_model_load(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        dataset = store.save_dataset({"name": "test", "samples": [email()]})
        events = []
        base = fake_factory(events)

        def factory(config_id, *args, **kwargs):
            adapter = base(config_id, *args, **kwargs)
            if config_id == "foundation_sec":
                async def failed_release():
                    events.append(("release", config_id))
                    return {"status": "ERROR", "unloaded": False, "error": {"type": "MODEL_UNLOAD_FAILED"}}
                adapter.release = failed_release
            return adapter

        engine = Engine(store, factory=factory)
        run = store.create_run(run_options(dataset["id"], ["foundation_sec", "qwen"]), {})
        await engine.execute(run["id"], True)
        saved = store.get_run(run["id"], True)
        assert ("prepare", "qwen") not in events
        assert saved["metrics"]["qwen"]["counts"]["ERROR"] == 1
        assert all(result["decision"] is None for result in saved["results"] if result["config_id"] == "qwen")

    asyncio.run(scenario())


def test_interrupted_run_retry_creates_new_attempt_from_original_snapshot(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(tmp_path)
    events = []
    app.state.engine.factory = fake_factory(events)
    with TestClient(app) as client:
        store = app.state.store
        dataset = store.save_dataset({"name": "test", "samples": [email("done"), email("unfinished")]})
        original = store.create_run(run_options(dataset["id"], ["qwen"]), {"temperature": 0})
        original["status"] = "RUNNING"
        store.update_run(original)
        for sample, status in zip(dataset["samples"], ("SUCCESS", "RUNNING")):
            row = app.state.engine._row(original, "qwen", sample)
            row.update(status=status, decision="NORMAL" if status == "SUCCESS" else None)
            store.save_result(row, True)
        store.recover()
        before = store.get_run(original["id"], True)
        assert before["status"] == "INTERRUPTED"
        assert before["metrics"]["qwen"]["counts"]["SKIPPED"] == 1
        # Removing the editable catalog entry cannot remove a run's snapshot.
        store.delete_dataset(dataset["id"])
        response = client.post(f"/api/runs/{original['id']}/retry")
        assert response.status_code == 200
        retried = response.json()
        assert retried["id"] != original["id"]
        assert retried["parent_run_id"] == original["id"]
        assert [sample["sample_id"] for sample in retried["dataset_snapshot"]["samples"]] == ["unfinished"]
        assert retried["settings"]["temperature"] == 0
        after = store.get_run(original["id"], True)
        assert after["results"] == before["results"]
        assert after["dataset_snapshot"] == before["dataset_snapshot"]
