"""Streaming boundaries use isolated HTTP fixtures, never dashboard seed data."""

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend import main


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


def read_events(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


class StreamingReportTests(unittest.TestCase):
    def setUp(self):
        main.generation_lock = asyncio.Lock()
        self.client = TestClient(main.app)
        self.request = {"title": "Stream boundary", "input_data": "  원본 입력\n\n"}
        self.output = {"classification": "NO_EVIDENCE", "findings": []}
        self.thoughts = ["첫 번째 줄\n", '따옴표 "와" 역슬래시 \\']

    def transport(self, handler):
        original = httpx.AsyncClient
        return patch("backend.main.httpx.AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    def stream_response(self, chunks):
        encoded = ("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n").encode()
        # Deliberately split in the middle of UTF-8 characters and JSON tokens.
        self.upstream = ChunkStream([encoded[i:i + 7] for i in range(0, len(encoded), 7)])
        return httpx.Response(200, stream=self.upstream, headers={"Content-Type": "application/x-ndjson"})

    def success_chunks(self):
        content = json.dumps(self.output, ensure_ascii=False)
        return [
            {"message": {"thinking": self.thoughts[0]}, "done": False},
            {"message": {"thinking": self.thoughts[1]}, "done": False},
            {"message": {"content": content[:20]}, "done": False},
            {"message": {"content": content[20:]}, "done": False},
            {"message": {"content": ""}, "done": True, "done_reason": "stop"},
        ]

    def post(self, handler):
        with self.transport(handler):
            return self.client.post("/api/reports/generate/stream", json=self.request)

    def test_tokens_arrive_before_validated_result_and_are_preserved(self):
        calls = []

        def handler(request):
            calls.append(request)
            return self.stream_response(self.success_chunks())

        response = self.post(handler)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = read_events(response)
        names = [name for name, data in events]
        self.assertLess(names.index("thinking"), names.index("content"))
        self.assertEqual(names[-1], "result")
        thoughts = "".join(data["text"] for name, data in events if name == "thinking")
        self.assertEqual(thoughts, "".join(self.thoughts))
        report = events[-1][1]["report"]
        self.assertEqual(report["thinking"], thoughts)
        self.assertEqual(report["input_data"], self.request["input_data"])
        payload = json.loads(calls[0].content)
        self.assertTrue(payload["stream"])
        self.assertTrue(payload["think"])
        self.assertEqual(payload["format"]["type"], "object")
        self.assertEqual(payload["format"]["required"], ["classification", "findings"])
        self.assertEqual(payload["model"], main.OLLAMA_MODEL)
        self.assertEqual(payload["messages"][0]["content"], main.SYSTEM_PROMPT)
        self.assertEqual(payload["messages"][1]["content"], self.request["input_data"])
        self.assertTrue(self.upstream.closed)
        self.assertFalse(main.generation_lock.locked())

    def test_no_thinking_emitted_means_empty_log(self):
        chunks = [chunk for chunk in self.success_chunks() if "thinking" not in chunk["message"]]
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        self.assertNotIn("thinking", [name for name, data in events])
        self.assertEqual(events[-1][1]["report"]["thinking"], "")

    def test_stream_constrains_one_report_and_exact_source_excerpts_while_keeping_thinking(self):
        self.request["input_data"] = 'GET /a HTTP/1.1\r\nHost: lab.test.local\r\n\r\nBody: "exact quote"\r\n'
        calls = []

        def handler(request):
            calls.append(json.loads(request.content))
            return self.stream_response(self.success_chunks())

        events = read_events(self.post(handler))
        payload = calls[0]
        self.assertIsInstance(payload.get("format"), dict)
        schema = payload["format"]
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        excerpts = schema["$defs"]["Finding"]["properties"]["evidence"]["items"]["enum"]
        self.assertIn('GET /a HTTP/1.1\r\nHost: lab.test.local', excerpts)
        self.assertIn('Body: "exact quote"', excerpts)
        self.assertTrue(all(excerpt in self.request["input_data"] and excerpt.strip() for excerpt in excerpts))
        self.assertNotIn('GET /a HTTP/1.1 Host: lab.test.local', excerpts)
        self.assertTrue(payload["think"])
        self.assertEqual(payload["messages"][1]["content"], self.request["input_data"])
        self.assertIn("thinking", [name for name, data in events])
        self.assertEqual(events[-1][0], "result")

    def test_sequential_json_reports_are_rejected_with_a_specific_error(self):
        raw = json.dumps(self.output) + '\n' + json.dumps(self.output)
        chunks = [{"message": {"thinking": "real thinking", "content": raw}, "done": True}]
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        self.assertEqual(events[-1][0], "error")
        self.assertIn("JSON", events[-1][1]["message"])
        self.assertNotIn("입력 근거를 확인", events[-1][1]["message"])
        self.assertEqual(events[-1][1]["code"], "invalid_json")
        self.assertIn("thinking", [name for name, data in events])
        self.assertNotIn("result", [name for name, data in events])

    def test_schema_error_identifies_missing_field_without_exposing_input(self):
        finding = {"target": "lab.test.local", "classification": "ATTACK_SURFACE", "vulnerability_type": None,
                   "CWE": None, "OWASP": None, "evidence": [self.request["input_data"]],
                   "confidence": None, "reason_validation_is_needed": None}
        raw = json.dumps({"classification": "ATTACK_SURFACE", "findings": [finding]})
        chunks = [{"message": {"thinking": "real thinking", "content": raw}, "done": True}]
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(events[-1][1].get("code"), "invalid_report")
        self.assertIn("findings.0.endpoint", events[-1][1]["message"])
        self.assertNotIn(self.request["input_data"], events[-1][1]["message"])

    def test_explicit_cases_require_enough_findings_in_generation_and_validation(self):
        self.request["input_data"] = '[CASE-001]\nGET /one HTTP/1.1\n\n[CASE-002]\nGET /two HTTP/1.1\n'
        calls = []
        self.output = {"classification": "ATTACK_SURFACE", "findings": [{
            "target": None, "endpoint": "/one", "classification": "ATTACK_SURFACE",
            "vulnerability_type": None, "CWE": None, "OWASP": None,
            "evidence": ["GET /one HTTP/1.1"], "confidence": None,
            "reason_validation_is_needed": None,
        }]}

        def handler(request):
            calls.append(json.loads(request.content))
            return self.stream_response(self.success_chunks())

        events = read_events(self.post(handler))
        self.assertEqual(calls[0]["format"]["properties"]["findings"].get("minItems"), 2)
        self.assertEqual(events[-1][0], "error")
        self.assertIn("2개 사례", events[-1][1]["message"])
        self.assertNotIn("result", [name for name, data in events])

    def test_implicit_model_thinking_is_split_at_fragmented_delimiter(self):
        raw = "first line\nsecond line\n</think>\n" + json.dumps(self.output)
        chunks = [{"message": {"content": char}, "done": False} for char in raw]
        chunks.append({"message": {}, "done": True})
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        names = [name for name, data in events]
        self.assertEqual(names[-1], "result")
        self.assertLess(names.index("thinking"), names.index("content"))
        self.assertEqual(events[-1][1]["report"]["thinking"], "first line\nsecond line\n")
        content = "".join(data["text"] for name, data in events if name == "content")
        self.assertEqual(json.loads(content), self.output)

    def test_explicit_raw_thinking_tag_is_not_displayed(self):
        raw = "<think>raw thought</think>" + json.dumps(self.output)
        chunks = [{"message": {"content": char}, "done": False} for char in raw]
        chunks.append({"message": {}, "done": True})
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        self.assertEqual(events[-1][1]["report"]["thinking"], "raw thought")

    def test_unfinished_raw_thinking_never_creates_report(self):
        chunks = [{"message": {"content": "unfinished thought </thi"}, "done": True}]
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        self.assertEqual(events[-1][0], "error")
        self.assertNotIn("result", [name for name, data in events])

    def test_truncated_stream_does_not_store_a_report(self):
        events = read_events(self.post(lambda request: self.stream_response(self.success_chunks()[:-1])))
        self.assertEqual(events[-1][0], "error")
        self.assertNotIn("result", [name for name, data in events])
        self.assertFalse(main.generation_lock.locked())

    def test_invalid_report_keeps_thoughts_but_returns_error(self):
        chunks = [{"message": {"thinking": "partial log", "content": "invalid"}, "done": True}]
        events = read_events(self.post(lambda request: self.stream_response(chunks)))
        self.assertIn("thinking", [name for name, data in events])
        self.assertEqual(events[-1][0], "error")
        self.assertFalse(main.generation_lock.locked())

    def test_invented_evidence_is_rejected_in_stream(self):
        self.output = {"classification": "INFORMATIONAL", "findings": [{
            "target": None, "endpoint": None, "classification": "INFORMATIONAL",
            "vulnerability_type": None, "CWE": None, "OWASP": None,
            "evidence": ["absent evidence"], "confidence": None, "reason_validation_is_needed": None,
        }]}
        events = read_events(self.post(lambda request: self.stream_response(self.success_chunks())))
        self.assertEqual(events[-1][0], "error")
        self.assertIn("입력에 없는 근거", events[-1][1]["message"])

    def test_ollama_error_returns_error_event_and_releases_lock(self):
        events = read_events(self.post(lambda request: self.stream_response([{"error": "runner failed"}])))
        self.assertEqual(events[-1][0], "error")
        self.assertFalse(main.generation_lock.locked())

    def test_missing_model_returns_error_event(self):
        events = read_events(self.post(lambda request: httpx.Response(404)))
        self.assertEqual(events[-1][0], "error")
        self.assertIn("모델을 찾을 수 없습니다", events[-1][1]["message"])
        self.assertFalse(main.generation_lock.locked())

    def test_busy_request_is_rejected_before_stream_headers(self):
        asyncio.run(main.generation_lock.acquire())
        try:
            response = self.post(lambda request: self.fail("Busy request must not call Ollama"))
            self.assertEqual(response.status_code, 409)
            self.assertNotIn("text/event-stream", response.headers["content-type"])
        finally:
            main.generation_lock.release()

    def test_disconnection_closes_upstream_and_releases_lock(self):
        async def run():
            with self.transport(lambda request: self.stream_response(self.success_chunks())):
                response = await main.generate_report_stream(main.GenerateRequest(**self.request))
                iterator = response.body_iterator
                await iterator.__anext__()  # connecting
                await iterator.__anext__()  # receiving
                await iterator.__anext__()  # thinking
                self.assertTrue(main.generation_lock.locked())
                await iterator.aclose()
                self.assertTrue(self.upstream.closed)
                self.assertFalse(main.generation_lock.locked())
                # The background cleanup must never release a subsequent request's lock.
                await main.generation_lock.acquire()
                await response.background()
                self.assertTrue(main.generation_lock.locked())
                main.generation_lock.release()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
