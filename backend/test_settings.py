"""Ollama settings boundaries use temporary files and isolated HTTP fixtures."""

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend import main
from backend.settings import SettingsConflict, SettingsError, SettingsStore, parse_modelfile, validate_ollama_url


INITIAL_MODELFILE = '''# Preserve this editor comment.
FROM fixture-base:latest
SYSTEM """
Saved fixture prompt.
Keep # characters and "quoted" text.
"""
PARAMETER temperature 0.1
'''
CHANGED_MODELFILE = '''# A different installed model selected in the editor.
FROM fixture-custom:7b
SYSTEM """
Updated fixture prompt.
Read only the exact user input.
"""
PARAMETER temperature 0.35
PARAMETER top_p 0.7
PARAMETER num_ctx 8192
PARAMETER num_predict 256
PARAMETER stop "END # marker"
PARAMETER stop "DONE"
'''


class ModelfileParserTests(unittest.TestCase):
    def test_multiline_system_preserves_hash_quotes_indentation_and_blank_lines(self):
        source = '''# Outside comment must not become a message.
FROM fixture-base:latest
SYSTEM """First line # stays inside the prompt.
  Indented "quoted" line with a \\ backslash.

Last line.
""" # End-of-block comment.
# Another outside comment.
PARAMETER stop "END # marker"
'''
        model, system, options = parse_modelfile(source)
        self.assertEqual(model, "fixture-base:latest")
        self.assertEqual(system, 'First line # stays inside the prompt.\n  Indented "quoted" line with a \\ backslash.\n\nLast line.')
        self.assertEqual(options["stop"], ["END # marker"])

    def test_quoted_single_line_system_and_stops_preserve_escaped_strings(self):
        source = r'''FROM "fixture-base:latest"
SYSTEM "Quoted \"text\", a \\ path, and # literal\nnext line."
PARAMETER stop "a\"b\\c"
PARAMETER stop "another\nline"
'''
        model, system, options = parse_modelfile(source)
        self.assertEqual(model, "fixture-base:latest")
        self.assertEqual(system, 'Quoted "text", a \\ path, and # literal\nnext line.')
        self.assertEqual(options["stop"], ['a"b\\c', 'another\nline'])

    def test_supported_numeric_parameters_use_numbers_and_repeated_stops_form_a_list(self):
        source = '''FROM fixture-base
SYSTEM "Fixture prompt."
PARAMETER temperature 1.25
PARAMETER top_p 0.75
PARAMETER min_p 0.05
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 8192
PARAMETER num_predict 128
PARAMETER top_k 42
PARAMETER seed 123
PARAMETER repeat_last_n -1
PARAMETER stop "first"
PARAMETER stop "second"
'''
        self.assertEqual(parse_modelfile(source)[2], {
            "temperature": 1.25, "top_p": 0.75, "min_p": 0.05,
            "repeat_penalty": 1.1, "num_ctx": 8192, "num_predict": 128,
            "top_k": 42, "seed": 123, "repeat_last_n": -1,
            "stop": ["first", "second"],
        })

    def test_missing_empty_and_unsupported_directives_are_rejected(self):
        invalid = [
            "", "# Only a comment\n", "FROM fixture-base\n",
            'SYSTEM "prompt"\n', 'FROM fixture-base\nSYSTEM ""\n',
            'FROM fixture-base\nSYSTEM "prompt"\nTEMPLATE "unsupported"\n',
            'FROM fixture-base\nSYSTEM "prompt"\nMESSAGE user "unsupported"\n',
            'FROM fixture-base\nSYSTEM "prompt"\nPARAMETER unknown 1\n',
        ]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(SettingsError):
                parse_modelfile(source)

    def test_duplicate_from_system_and_numeric_parameters_are_rejected(self):
        invalid = [
            'FROM fixture-base\nFROM fixture-other\nSYSTEM "prompt"\n',
            'FROM fixture-base\nSYSTEM "prompt"\nSYSTEM "other"\n',
            'FROM fixture-base\nSYSTEM "prompt"\nPARAMETER temperature 0.1\nPARAMETER temperature 0.2\n',
        ]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(SettingsError):
                parse_modelfile(source)

    def test_invalid_numbers_and_parameter_bounds_are_rejected(self):
        invalid_parameters = [
            "temperature NaN", "temperature inf", "temperature -0.1", "temperature 2.1",
            "top_p 1.1", "num_ctx 511", "num_ctx 4096.5", "num_predict 0",
            "seed -1", "stop \"\"",
        ]
        for parameter in invalid_parameters:
            with self.subTest(parameter=parameter), self.assertRaises(SettingsError):
                parse_modelfile(f'FROM fixture-base\nSYSTEM "prompt"\nPARAMETER {parameter}\n')

    def test_oversized_integer_is_a_validation_error(self):
        # A bounded editor field must not turn an invalid number into an API 500.
        with self.assertRaises(SettingsError):
            parse_modelfile('FROM fixture-base\nSYSTEM "prompt"\nPARAMETER num_ctx ' + "9" * 400 + "\n")

    def test_unterminated_or_malformed_strings_and_block_suffixes_are_rejected(self):
        invalid = [
            'FROM fixture-base\nSYSTEM """unfinished\n',
            'FROM fixture-base\nSYSTEM "unfinished\n',
            'FROM fixture-base\nSYSTEM """prompt""" FROM fixture-other\n',
            'FROM fixture-base\nSYSTEM "prompt"\nPARAMETER stop "unfinished\n',
        ]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(SettingsError):
                parse_modelfile(source)

    def test_from_rejects_local_paths_urls_and_empty_or_dot_segments(self):
        invalid = [
            "C:/models/fixture.gguf", "C:\\models\\fixture.gguf", "/models/fixture.gguf",
            "./fixture.gguf", "../fixture.gguf", "hf.co//fixture", "hf.co/./fixture",
            "hf.co/../fixture", "https://example.com/fixture", "fixture/",
        ]
        for model in invalid:
            with self.subTest(model=model), self.assertRaises(SettingsError):
                parse_modelfile(f'FROM {model}\nSYSTEM "prompt"\n')

    def test_from_accepts_registry_namespace_model_names(self):
        model, system, options = parse_modelfile('FROM hf.co/fixture-org/fixture-model:Q4_K_M\nSYSTEM "prompt"\n')
        self.assertEqual(model, "hf.co/fixture-org/fixture-model:Q4_K_M")


class OllamaUrlTests(unittest.TestCase):
    def test_only_local_origins_are_accepted_and_normalized(self):
        cases = [
            (" http://127.0.0.1:11434/ ", "http://127.0.0.1:11434"),
            ("HTTP://LOCALHOST:12345/", "http://localhost:12345"),
            ("https://[::1]:11434/", "https://[::1]:11434"),
            ("http://127.0.0.2", "http://127.0.0.2"),
        ]
        for supplied, expected in cases:
            with self.subTest(supplied=supplied):
                self.assertEqual(validate_ollama_url(supplied), expected)

    def test_external_credentials_paths_queries_fragments_and_invalid_ports_are_rejected(self):
        invalid = [
            "http://example.com:11434", "https://8.8.8.8", "http://192.168.1.2:11434",
            "http://0.0.0.0:11434", "http://localhost.example.com:11434",
            "http://user:password@localhost:11434", "http://user@127.0.0.1:11434",
            "http://localhost:11434/api", "http://localhost:11434/?model=fixture",
            "http://localhost:11434/#fragment", "ftp://localhost:11434",
            "http://localhost:0", "http://localhost:65536", "http://localhost:abc",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(SettingsError):
                validate_ollama_url(url)


class TemporarySettingsTestCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.modelfile = self.directory / "Modelfile"
        self.runtime_file = self.directory / ".ollama-settings.json"
        self.modelfile.write_bytes(INITIAL_MODELFILE.encode("utf-8"))
        self.store = SettingsStore(self.modelfile, self.runtime_file, "http://127.0.0.1:11434")

    def files(self):
        return self.modelfile.read_bytes(), self.runtime_file.read_bytes() if self.runtime_file.exists() else None

    def save_data(self, **changes):
        data = {
            "ollama_url": "http://localhost:12345/", "modelfile": CHANGED_MODELFILE,
            "keep_alive": "15m", "revision": self.store.load().revision,
        }
        data.update(changes)
        return data


class SettingsStoreTests(TemporarySettingsTestCase):
    def test_save_persists_exact_editor_text_and_runtime_settings_for_a_new_store(self):
        old_revision = self.store.load().revision
        saved = self.store.save(**self.save_data())
        self.assertEqual(self.modelfile.read_bytes(), CHANGED_MODELFILE.encode())
        self.assertEqual(json.loads(self.runtime_file.read_text(encoding="utf-8")), {
            "ollama_url": "http://localhost:12345", "keep_alive": "15m",
        })
        reloaded = SettingsStore(self.modelfile, self.runtime_file, "http://127.0.0.1:9999").load()
        self.assertEqual(reloaded, saved)
        self.assertNotEqual(reloaded.revision, old_revision)
        self.assertEqual(reloaded.system_prompt, "Updated fixture prompt.\nRead only the exact user input.")

    def test_stale_revision_cannot_overwrite_a_newer_save(self):
        stale = self.store.load().revision
        self.store.save(**self.save_data())
        before = self.files()
        with self.assertRaises(SettingsConflict):
            self.store.save(**self.save_data(revision=stale, modelfile=INITIAL_MODELFILE))
        self.assertEqual(self.files(), before)

    def test_revision_changes_when_modelfile_is_edited_outside_the_app(self):
        stale = self.store.load().revision
        self.modelfile.write_text(INITIAL_MODELFILE + "# External edit\n", encoding="utf-8")
        before = self.files()
        with self.assertRaises(SettingsConflict):
            self.store.save(**self.save_data(revision=stale))
        self.assertEqual(self.files(), before)

    def check_runtime_failure_rollback(self, existing_runtime):
        if existing_runtime:
            self.runtime_file.write_text('{"ollama_url":"http://127.0.0.1:11434","keep_alive":"1m"}', encoding="utf-8")
        before = self.files()
        old_settings = self.store.load()
        real_replace = self.store.replace_file
        failed = False

        def replace_once(path, content):
            nonlocal failed
            if path == self.runtime_file and not failed:
                failed = True
                raise OSError("Simulated runtime settings write failure")
            real_replace(path, content)

        with patch.object(self.store, "replace_file", side_effect=replace_once), self.assertRaises(OSError):
            self.store.save(**self.save_data())
        self.assertEqual(self.files(), before)
        self.assertEqual(self.store.load(), old_settings)

    def test_runtime_write_failure_restores_previous_modelfile_and_existing_runtime(self):
        self.check_runtime_failure_rollback(existing_runtime=True)

    def test_runtime_write_failure_restores_modelfile_without_creating_a_runtime_file(self):
        self.check_runtime_failure_rollback(existing_runtime=False)


class OllamaSettingsApiTests(TemporarySettingsTestCase):
    def setUp(self):
        super().setUp()
        store_patch = patch("backend.main.settings_store", self.store)
        lock_patch = patch("backend.main.generation_lock", asyncio.Lock())
        store_patch.start()
        lock_patch.start()
        self.addCleanup(store_patch.stop)
        self.addCleanup(lock_patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.request = {"title": "Private fixture title", "input_data": "  원본 입력 # exactly\r\n\tGET /fixture\r\n\r\n"}

    def transport(self, handler):
        original = httpx.AsyncClient
        return patch("backend.main.httpx.AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    def assert_settings_unchanged(self, before):
        self.assertEqual(self.files(), before)

    def test_get_reads_saved_settings_without_creating_files(self):
        before = self.files()
        response = self.client.get("/api/settings/ollama")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["modelfile"], INITIAL_MODELFILE)
        self.assertEqual(response.json()["model"], "fixture-base:latest")
        self.assertEqual(response.json()["ollama_url"], "http://127.0.0.1:11434")
        self.assertEqual(response.json()["keep_alive"], "5m")
        self.assert_settings_unchanged(before)

    def test_put_and_following_get_return_persisted_settings_and_new_revision(self):
        initial = self.client.get("/api/settings/ollama").json()
        response = self.client.put("/api/settings/ollama", json=self.save_data())
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual(saved["modelfile"], CHANGED_MODELFILE)
        self.assertEqual(saved["model"], "fixture-custom:7b")
        self.assertEqual(saved["ollama_url"], "http://localhost:12345")
        self.assertEqual(saved["keep_alive"], "15m")
        self.assertNotEqual(saved["revision"], initial["revision"])
        self.assertEqual(self.client.get("/api/settings/ollama").json(), saved)
        self.assertEqual(self.modelfile.read_bytes(), CHANGED_MODELFILE.encode())

    def test_stale_revision_returns_409_without_writes(self):
        stale = self.save_data()
        self.assertEqual(self.client.put("/api/settings/ollama", json=stale).status_code, 200)
        before = self.files()
        response = self.client.put("/api/settings/ollama", json={**stale, "modelfile": INITIAL_MODELFILE})
        self.assertEqual(response.status_code, 409)
        self.assert_settings_unchanged(before)

    def test_generating_returns_409_without_writes(self):
        before = self.files()
        asyncio.run(main.generation_lock.acquire())
        try:
            response = self.client.put("/api/settings/ollama", json=self.save_data())
            self.assertEqual(response.status_code, 409)
            self.assert_settings_unchanged(before)
        finally:
            main.generation_lock.release()

    def test_invalid_draft_returns_422_without_writes_or_ollama_calls(self):
        before = self.files()
        changes = [
            {"ollama_url": "http://example.com:11434"},
            {"modelfile": 'FROM fixture-base\nSYSTEM "prompt"\nPARAMETER temperature NaN\n'},
            {"modelfile": 'FROM fixture-base\nSYSTEM "prompt"\nMESSAGE user "other report"\n'},
            {"keep_alive": "forever"},
        ]
        with self.transport(lambda request: self.fail("Saving configuration must not call Ollama")):
            for change in changes:
                with self.subTest(change=change):
                    response = self.client.put("/api/settings/ollama", json=self.save_data(**change))
                    self.assertEqual(response.status_code, 422)
                    self.assert_settings_unchanged(before)

    def test_oversized_integer_returns_422_without_writes(self):
        before = self.files()
        draft = 'FROM fixture-base\nSYSTEM "prompt"\nPARAMETER num_ctx ' + "9" * 400 + "\n"
        response = self.client.put("/api/settings/ollama", json=self.save_data(modelfile=draft))
        self.assertEqual(response.status_code, 422)
        self.assert_settings_unchanged(before)

    def test_save_write_failure_returns_503_and_restores_original_modelfile(self):
        before = self.files()
        real_replace = self.store.replace_file
        failed = False

        def replace_once(path, content):
            nonlocal failed
            if path == self.runtime_file and not failed:
                failed = True
                raise OSError("Simulated runtime write failure")
            real_replace(path, content)

        with patch.object(self.store, "replace_file", side_effect=replace_once):
            response = self.client.put("/api/settings/ollama", json=self.save_data())
        self.assertEqual(response.status_code, 503)
        self.assert_settings_unchanged(before)

    def test_generation_after_save_uses_new_model_prompt_options_url_and_exact_input(self):
        self.assertEqual(self.client.put("/api/settings/ollama", json=self.save_data()).status_code, 200)
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(str(request.url), "http://localhost:12345/api/chat")
            return httpx.Response(200, json={"message": {"content": '{"classification":"NO_EVIDENCE","findings":[]}'}, "done": True})

        with self.transport(handler):
            first = self.client.post("/api/reports/generate", json=self.request)
            second_input = "  A second request has no previous report context.\n\n"
            second = self.client.post("/api/reports/generate", json={**self.request, "input_data": second_input})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["model"], "fixture-custom:7b")
        self.assertEqual(first.json()["input_data"], self.request["input_data"])
        self.assertEqual(len(calls), 2)
        for request, user_input in zip(calls, [self.request["input_data"], second_input]):
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "fixture-custom:7b")
            self.assertEqual(payload["messages"], [
                {"role": "system", "content": "Updated fixture prompt.\nRead only the exact user input."},
                {"role": "user", "content": user_input},
            ])
            self.assertEqual(payload["options"], {
                "temperature": 0.35, "top_p": 0.7, "repeat_penalty": 1.0,
                "num_ctx": 8192, "num_predict": 256, "stop": ["END # marker", "DONE"],
            })
            self.assertEqual(payload["keep_alive"], "15m")
            self.assertFalse(payload["stream"])
            self.assertFalse(payload["think"])

    def test_health_after_save_uses_saved_url_and_reports_saved_installed_model(self):
        self.assertEqual(self.client.put("/api/settings/ollama", json=self.save_data()).status_code, 200)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"models": [{"name": "fixture-custom:7b"}]})

        with self.transport(handler):
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([str(request.url) for request in calls], ["http://localhost:12345/api/tags"])
        self.assertEqual(response.json()["model"], "fixture-custom:7b")
        self.assertEqual(response.json()["ollama_url"], "http://localhost:12345")
        self.assertTrue(response.json()["ollama_available"])
        self.assertTrue(response.json()["model_connected"])

    def test_model_listing_returns_actual_tags_and_preserves_model_metadata(self):
        installed = [{
            "name": "fixture-installed:latest", "model": "fixture-installed:latest",
            "modified_at": "2026-10-01T00:00:00Z", "size": 12345, "digest": "fixture-digest",
            "details": {"format": "gguf", "family": "fixture", "parameter_size": "1B", "quantization_level": "Q4_K_M"},
        }]
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"models": installed})

        with self.transport(handler):
            response = self.client.get("/api/ollama/models", params={"ollama_url": "http://localhost:12345/"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([str(request.url) for request in calls], ["http://localhost:12345/api/tags"])
        self.assertEqual(response.json()["models"], installed)
        self.assertTrue(response.json()["ollama_available"])

    def test_empty_installed_models_do_not_receive_fallback_models(self):
        with self.transport(lambda request: httpx.Response(200, json={"models": []})):
            response = self.client.get("/api/ollama/models")
        self.assertTrue(response.json()["ollama_available"])
        self.assertEqual(response.json()["models"], [])

    def test_offline_or_invalid_model_lists_return_no_fallback_models(self):
        def offline(request):
            raise httpx.ConnectError("Fixture server offline", request=request)

        handlers = [offline, lambda request: httpx.Response(200, json={"models": [{"name": 42}]})]
        for handler in handlers:
            with self.subTest(handler=handler), self.transport(handler):
                response = self.client.get("/api/ollama/models")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["ollama_available"])
            self.assertEqual(response.json()["models"], [])

    def test_check_draft_uses_draft_url_model_and_does_not_mutate_saved_settings(self):
        before = self.files()
        saved = self.client.get("/api/settings/ollama").json()
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "draft-model:latest"}]})
            self.assertEqual(json.loads(request.content), {"model": "draft-model"})
            return httpx.Response(200, json={"capabilities": ["completion", "thinking", 42]})

        with self.transport(handler):
            response = self.client.post("/api/ollama/check", json={"ollama_url": "http://localhost:54321/", "model": "draft-model"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([str(request.url) for request in calls], ["http://localhost:54321/api/tags", "http://localhost:54321/api/show"])
        self.assertEqual(response.json()["model"], "draft-model")
        self.assertTrue(response.json()["model_connected"])
        self.assertEqual(response.json()["capabilities"], ["completion", "thinking"])
        self.assertEqual(self.client.get("/api/settings/ollama").json(), saved)
        self.assert_settings_unchanged(before)

    def test_uninstalled_draft_reports_disconnected_without_model_show_or_save(self):
        before = self.files()
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.path, "/api/tags")
            return httpx.Response(200, json={"models": [{"name": "other-model:latest"}]})

        with self.transport(handler):
            response = self.client.post("/api/ollama/check", json={"ollama_url": "http://localhost:54321", "model": "missing-model"})
        self.assertTrue(response.json()["ollama_available"])
        self.assertFalse(response.json()["model_connected"])
        self.assertEqual(len(calls), 1)
        self.assert_settings_unchanged(before)

    def test_invalid_check_and_list_urls_are_rejected_before_network_access(self):
        before = self.files()
        with self.transport(lambda request: self.fail("Invalid local URL must not make an HTTP call")):
            listed = self.client.get("/api/ollama/models", params={"ollama_url": "http://example.com:11434"})
            checked = self.client.post("/api/ollama/check", json={"ollama_url": "http://user@localhost:11434", "model": "draft-model"})
        self.assertEqual(listed.status_code, 422)
        self.assertEqual(checked.status_code, 422)
        self.assert_settings_unchanged(before)

    def test_non_thinking_model_stream_disables_thinking_and_uses_saved_settings(self):
        self.assertEqual(self.client.put("/api/settings/ollama", json=self.save_data()).status_code, 200)
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/api/show":
                self.assertEqual(json.loads(request.content), {"model": "fixture-custom:7b"})
                return httpx.Response(200, json={"capabilities": ["completion"]})
            self.assertEqual(str(request.url), "http://localhost:12345/api/chat")
            chunks = [
                {"message": {"content": '{"classification":"NO_EVIDENCE","findings":[]}'}, "done": False},
                {"message": {}, "done": True, "done_reason": "stop"},
            ]
            return httpx.Response(200, content="\n".join(json.dumps(chunk) for chunk in chunks), headers={"Content-Type": "application/x-ndjson"})

        with self.transport(handler):
            response = self.client.post("/api/reports/generate/stream", json=self.request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: result\n", response.text)
        self.assertNotIn("event: error\n", response.text)
        self.assertEqual([request.url.path for request in calls], ["/api/show", "/api/chat"])
        payload = json.loads(calls[-1].content)
        self.assertFalse(payload["think"])
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["keep_alive"], "15m")
        self.assertEqual(payload["options"]["temperature"], 0.35)
        self.assertEqual(payload["messages"], [
            {"role": "system", "content": "Updated fixture prompt.\nRead only the exact user input."},
            {"role": "user", "content": self.request["input_data"]},
        ])
        self.assertFalse(main.generation_lock.locked())


if __name__ == "__main__":
    unittest.main()
