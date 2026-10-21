"""Boundary checks without calling a live model or creating stored reports."""

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend import main


class ReportApiTests(unittest.TestCase):
    def setUp(self):
        main.generation_lock = asyncio.Lock()
        self.client = TestClient(main.app)
        self.request = {"title": "Boundary check", "input_data": "  GET /search?q=test HTTP/1.1\nHost: example.com\n\n"}
        self.output = {
            "classification": "ATTACK_SURFACE",
            "findings": [{
                "target": "example.com", "endpoint": "/search?q=test",
                "classification": "ATTACK_SURFACE", "vulnerability_type": None,
                "CWE": None, "OWASP": None, "evidence": ["GET /search?q=test HTTP/1.1"],
                "confidence": None, "reason_validation_is_needed": "HTTP response is missing.",
            }],
        }

    def transport(self, handler):
        original = httpx.AsyncClient
        return patch("backend.main.httpx.AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    def response(self, request):
        return httpx.Response(200, json={"message": {"content": json.dumps(self.output)}})

    def test_success_calls_exact_model_and_preserves_input(self):
        calls = []

        def handler(request):
            calls.append(request)
            return self.response(request)

        with self.transport(handler):
            response = self.client.post("/api/reports/generate", json=self.request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(calls[0].content)
        self.assertEqual(calls[0].url.path, "/api/chat")
        self.assertEqual(payload["model"], main.OLLAMA_MODEL)
        self.assertEqual(payload["messages"][0]["content"], main.SYSTEM_PROMPT)
        self.assertEqual(payload["messages"][1]["content"], self.request["input_data"])
        self.assertNotIn(self.request["title"], payload["messages"][1]["content"])
        self.assertEqual(response.json()["classification"], "ATTACK_SURFACE")
        self.assertEqual(response.json()["status"], "완료")
        self.assertEqual(response.json()["input_data"], self.request["input_data"])
        self.assertEqual(response.json()["target"], "example.com")

    def test_empty_input_is_rejected_before_model_call(self):
        with self.transport(lambda request: self.fail("Model must not be called")):
            response = self.client.post("/api/reports/generate", json={**self.request, "input_data": "  "})
        self.assertEqual(response.status_code, 422)

    def test_unavailable_ollama_returns_error_not_dummy_report(self):
        def handler(request):
            raise httpx.ConnectError("Offline", request=request)

        with self.transport(handler):
            response = self.client.post("/api/reports/generate", json=self.request)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("findings", response.json())

    def test_invalid_model_json_is_rejected(self):
        with self.transport(lambda request: httpx.Response(200, json={"message": {"content": "not json"}})):
            response = self.client.post("/api/reports/generate", json=self.request)
        self.assertEqual(response.status_code, 502)

    def test_invented_evidence_is_rejected(self):
        self.output["findings"][0]["evidence"] = ["An excerpt never supplied by the user"]
        with self.transport(self.response):
            response = self.client.post("/api/reports/generate", json=self.request)
        self.assertEqual(response.status_code, 502)

    def test_summary_classification_is_derived_from_validated_findings(self):
        self.output["classification"] = "CONFIRMED"
        with self.transport(self.response):
            response = self.client.post("/api/reports/generate", json=self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"], "ATTACK_SURFACE")
        self.assertEqual(response.json()["findings"][0]["classification"], "ATTACK_SURFACE")

    def test_strict_model_validation_still_rejects_an_inconsistent_summary(self):
        self.output["classification"] = "CONFIRMED"
        with self.assertRaises(main.ValidationError):
            main.ModelOutput.model_validate(self.output)

    def test_case_markers_preserve_crlf_and_do_not_turn_greetings_into_evidence(self):
        source = '[CASE-001]\r\nGET /one HTTP/1.1\r\n\r\n[CASE-002]\r\nPOST /two HTTP/1.1\r\n'
        self.assertEqual(main.explicit_case_count(source), 2)
        self.assertEqual(main.report_format(source)["properties"]["findings"]["minItems"], 2)
        greeting = '[CASE-001]\nhello\n[CASE-002]\nhi\n'
        self.assertEqual(main.explicit_case_count(greeting), 0)
        self.assertNotIn("minItems", main.report_format(greeting)["properties"]["findings"])

    def test_health_reports_installed_model(self):
        with self.transport(lambda request: httpx.Response(200, json={"models": [{"name": main.OLLAMA_MODEL}]})):
            response = self.client.get("/api/health")
        self.assertTrue(response.json()["model_connected"])

    def test_health_reports_disconnection(self):
        def handler(request):
            raise httpx.ConnectError("Offline", request=request)

        with self.transport(handler):
            response = self.client.get("/api/health")
        self.assertFalse(response.json()["model_connected"])


if __name__ == "__main__":
    unittest.main()
