"""Private YAML section selection, shared CLI loading and safe parse failures."""

from pathlib import Path
from contextlib import redirect_stdout
import io
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from policyweave.adapters.model_settings import LOCAL_PROVIDER, load_connection
from policyweave.adapters.coding import CodingAgent
from policyweave.adapters.compatible import Connection
from policyweave.adapters.model_proxy import ModelProxy
from tests.adapters.test_models import ModelFixture, proxy_request


class ConnectionFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "connection.yaml"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value):
        self.path.write_text(yaml.safe_dump(value))

    def test_auto_selects_only_filled_key_and_defaults_to_openai_when_both_filled(self):
        for keys, provider in ((dict(openai="synthetic-openai"), "openai"),
                               (dict(anthropic="synthetic-anthropic"), "anthropic"),
                               (dict(openai="synthetic-openai", anthropic="synthetic-anthropic"), "openai")):
            with self.subTest(provider=provider, count=len(keys)):
                self.write({name: dict(apiKey=keys.get(name, "")) for name in ("openai", "anthropic")})
                settings = load_connection(self.path)
                self.assertEqual(settings["apiKey"], keys[provider])
                self.assertEqual(settings["protocol"], "messages" if provider == "anthropic" else "chat-completions")
                self.assertNotIn("openai", settings)
                self.assertNotIn("anthropic", settings)
                inactive = "anthropic" if provider == "openai" else "openai"
                if inactive in keys:
                    self.assertNotIn(keys[inactive], repr(settings))
                with patch("policyweave.adapters.coding.shutil.which", return_value="/synthetic/coder") as which:
                    self.assertEqual(CodingAgent(settings).messages, provider == "anthropic")
                    self.assertEqual(which.call_args.args, ("claude" if provider == "anthropic" else "codex",))

    def test_explicit_provider_overrides_priority_and_does_not_fall_back(self):
        value = dict(provider="anthropic", openai=dict(apiKey="synthetic-openai"),
                     anthropic=dict(apiKey="synthetic-anthropic"))
        self.write(value)
        self.assertEqual(load_connection(self.path)["apiKey"], "synthetic-anthropic")
        value["anthropic"]["apiKey"] = ""
        self.write(value)
        with self.assertRaisesRegex(ValueError, "Selected provider"):
            load_connection(self.path)

    def test_blank_optional_section_is_ignored_and_keyless_endpoint_requires_explicit_choice(self):
        self.write(dict(openai=None, anthropic=dict(apiKey="synthetic")))
        self.assertEqual(load_connection(self.path)["protocol"], "messages")
        self.write(dict(openai=dict(apiKey=None), anthropic=dict(apiKey="synthetic")))
        self.assertEqual(load_connection(self.path)["protocol"], "messages")
        self.write(dict(openai=dict(baseUrl="http://127.0.0.1/v1", modelId="local")))
        with self.assertRaisesRegex(ValueError, "Fill apiKey"):
            load_connection(self.path)
        self.write(dict(provider="openai", openai=dict(baseUrl="http://127.0.0.1/v1", modelId="local")))
        self.assertEqual(load_connection(self.path)["modelId"], "local")

    def test_connection_objects_use_same_selected_file_and_only_selected_key(self):
        with ModelFixture() as fixture:
            for name, protocol in (("anthropic", "messages"), ("openai", "chat-completions")):
                self.write(dict(provider=name, **{key: dict(apiKey="synthetic-" + key,
                    baseUrl=fixture.base, modelId="fixture") for key in ("openai", "anthropic")}))
                model = Connection(load_connection(self.path))
                self.assertEqual(model("test", "data"), '{"ok":true}')
                self.assertEqual(model.metadata["transport"], protocol)
                self.assertNotIn("synthetic-", repr(model.metadata))
                request = fixture.requests[-1]
                headers = {key.lower(): value for key, value in request["headers"].items()}
                credential = headers.get("x-api-key") or headers.get("authorization")
                self.assertIn("synthetic-" + name, credential)

    def test_local_selection_requires_its_own_endpoint_and_model_without_hosted_defaults(self):
        local = dict(baseUrl="http://127.0.0.1:8000/v1", modelId="fixture-local")
        value = dict(provider=LOCAL_PROVIDER, openai=dict(apiKey="synthetic-inactive"),
                     **{LOCAL_PROVIDER: local})
        self.write(value)
        settings = load_connection(self.path)
        self.assertEqual(settings, dict(local, protocol="chat-completions"))
        for field in ("baseUrl", "modelId"):
            for key in ("", "synthetic-local"):
                with self.subTest(missing=field, authenticated=bool(key)):
                    self.write(dict(provider=LOCAL_PROVIDER,
                                    **{LOCAL_PROVIDER: {**local, field: "", "apiKey": key}}))
                    with self.assertRaises(ValueError):
                        load_connection(self.path)

    def test_auto_never_selects_local_even_with_a_key(self):
        local = dict(baseUrl="http://127.0.0.1/v1", modelId="fixture", apiKey="synthetic-local")
        self.write({LOCAL_PROVIDER: local})
        with self.assertRaisesRegex(ValueError, "explicitly select"):
            load_connection(self.path)
        self.write(dict(openai=dict(apiKey="synthetic-openai"),
                        anthropic=dict(apiKey="synthetic-anthropic"), **{LOCAL_PROVIDER: local}))
        self.assertEqual(load_connection(self.path)["apiKey"], "synthetic-openai")

    def test_local_invalid_connection_does_not_fall_back_to_hosted_key(self):
        for extra in (dict(baseUrl="http://example.invalid/v1"),
                      dict(protocol="messages"), dict(apiKey="synthetic\ninjection"),
                      dict(headers={"Authorization": "synthetic-override"})):
            self.write(dict(provider=LOCAL_PROVIDER, openai=dict(apiKey="synthetic-hosted"),
                            **{LOCAL_PROVIDER: dict(dict(baseUrl="http://127.0.0.1/v1",
                                                         modelId="fixture"), **extra)}))
            with self.assertRaises(ValueError):
                load_connection(self.path)

    def test_local_uses_shared_structured_transport_and_codex_without_hosted_reasoning(self):
        with ModelFixture() as fixture:
            for key in ("", "synthetic-local"):
                self.write(dict(provider=LOCAL_PROVIDER, **{LOCAL_PROVIDER: dict(
                    baseUrl=fixture.base, modelId="fixture-local", apiKey=key,
                    responseFormat=dict(type="json_schema", json_schema=dict(
                        name="fixture", strict=True, schema=dict(type="object"))))}))
                settings = load_connection(self.path)
                self.assertEqual(Connection(settings)("plan", "fixture data"), '{"ok":true}')
                request = fixture.requests[-1]
                self.assertEqual(request["path"], "/v1/chat/completions")
                self.assertEqual(request["payload"]["model"], "fixture-local")
                self.assertEqual(request["payload"]["max_completion_tokens"], 12000)
                self.assertEqual(request["payload"]["response_format"], settings["responseFormat"])
                self.assertNotIn("reasoning_effort", request["payload"])
                headers = {name.lower(): value for name, value in request["headers"].items()}
                self.assertEqual(headers.get("authorization"), "Bearer " + key if key else None)
                with patch("policyweave.adapters.coding.shutil.which", return_value="/synthetic/coder") as which:
                    coder = CodingAgent(settings)
                self.assertEqual(which.call_args.args, ("codex",))
                self.assertEqual(coder.protocol, "responses")
                self.assertEqual(coder.name, "codex-exec")
                command = coder.arguments("stage")
                self.assertIn("fixture-local", command)
                self.assertTrue(any('wire_api="responses"' in arg for arg in command))
                self.assertFalse(any("model_reasoning_effort" in arg for arg in command))
                self.assertNotIn("synthetic-local", repr(command + coder.environment() + coder.mounts()))

    def test_local_responses_relay_preserves_stream_tools_and_results_and_restricts_routes(self):
        with ModelFixture() as fixture:
            self.write(dict(provider=LOCAL_PROVIDER, **{LOCAL_PROVIDER: dict(
                baseUrl=fixture.base, modelId="fixture-local")}))
            fixture.headers["Content-Type"] = "text/event-stream"
            fixture.reply = b'event: response.completed\ndata: {"type":"response.completed"}\n\n'
            with ModelProxy(self.temp.name, load_connection(self.path)) as proxy:
                tools = [dict(type="function", name="fixture", parameters=dict(type="object"))]
                for item in (dict(role="user", content="fixture data"),
                             dict(type="function_call_output", call_id="fixture-call", output="done")):
                    payload = dict(model="fixture-local", stream=True, tools=tools, input=[item])
                    status, body, content_type = proxy_request(proxy, "/v1/responses", payload)
                    self.assertEqual((status, body, content_type), (200, fixture.reply, "text/event-stream"))
                    request = fixture.requests[-1]
                    self.assertEqual(request["path"], "/v1/responses")
                    self.assertEqual(request["payload"], payload)
                    self.assertNotIn("authorization", {name.lower() for name in request["headers"]})
                before = len(fixture.requests)
                self.assertEqual(proxy_request(proxy, "/v1/chat/completions", payload)[0], 404)
                self.assertEqual(proxy_request(proxy, "/v1/responses", dict(model="other"))[0], 400)
                self.assertEqual(len(fixture.requests), before)

    def test_public_template_can_select_each_connection(self):
        template = yaml.safe_load((Path(__file__).resolve().parents[2] / "examples/connection.yaml").read_text())
        for name, protocol in (("openai", "chat-completions"), ("anthropic", "messages"),
                               (LOCAL_PROVIDER, "chat-completions")):
            template["provider"] = name
            if name == LOCAL_PROVIDER:
                template[name].update(baseUrl="http://127.0.0.1/v1", modelId="fixture-local")
            else:
                template[name]["apiKey"] = "synthetic-" + name
            self.write(template)
            self.assertEqual(load_connection(self.path)["protocol"], protocol)

    def test_course_yaml_matches_public_template_and_hosted_defaults(self):
        root = Path(__file__).resolve().parents[2]
        course = root / "docs/phase2-hw-release/phase2-instructions.tex"
        if not course.is_file():
            self.skipTest("Optional course submodule is not initialized")
        source = course.read_text()
        snippet = source.split("cat > \"$CONNECTION_FILE\" <<'YAML'\n", 1)[1].split("\nYAML", 1)[0]
        template = yaml.safe_load((root / "examples/connection.yaml").read_text())
        self.assertEqual(yaml.safe_load(snippet), template)
        for name in ("openai", "anthropic"):
            self.write({name: dict(apiKey="synthetic")})
            settings = load_connection(self.path)
            self.assertEqual(settings["modelId"], template[name]["modelId"])
            self.assertEqual(settings["reasoningEffort"], template[name]["reasoningEffort"])

    def test_rejects_json_files_flat_configs_and_unknown_sections(self):
        self.path = self.path.with_suffix(".json")
        self.path.write_text('{"apiKey":"synthetic-private"}')
        with self.assertRaisesRegex(ValueError, "yaml or .yml"):
            load_connection(self.path)
        self.path = self.path.with_suffix(".yaml")
        for value in (dict(apiKey="synthetic-private"), dict(antropic=dict(apiKey="synthetic-private")),
                      dict(provider="unknown"), dict(openai=False), dict(openai=dict(api_key="synthetic-private")),
                      dict(anthropic=dict(apiKey="synthetic", protocol="chat-completions"))):
            self.write(value)
            with self.assertRaises(ValueError) as error:
                load_connection(self.path)
            self.assertNotIn("synthetic-private", str(error.exception))

    def test_yaml_errors_duplicates_aliases_and_unsafe_tags_never_echo_secrets(self):
        for document in (
            'openai:\n  apiKey: "synthetic-private\n',
            'openai:\n  apiKey: synthetic-private\n  apiKey: another\n',
            'openai: !!python/object/apply:builtins.str [synthetic-private]\n',
            'openai: &a {apiKey: synthetic-private}\nanthropic: *a\n',
            'openai: {apiKey: synthetic-private}\n---\nother: value\n',
            'openai: {apiKey: "synthetic-private\\nextra"}\n',
        ):
            self.path.write_text(document)
            with self.assertRaises(ValueError) as error:
                load_connection(self.path)
            self.assertNotIn("synthetic-private", str(error.exception))

    def test_size_and_nesting_limits(self):
        self.path.write_bytes(b"x" * 65_537)
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            load_connection(self.path)
        self.path.write_text("[" * 40 + "0" + "]" * 40)
        with self.assertRaises(ValueError):
            load_connection(self.path)

    def test_inspect_and_review_cli_load_same_yaml_without_a_coding_cli(self):
        from policyweave.workbench import analysis
        from policyweave.workbench import __main__ as review

        for value, protocol in (
            (dict(anthropic=dict(apiKey="synthetic")), "messages"),
            (dict(provider=LOCAL_PROVIDER, **{LOCAL_PROVIDER: dict(
                baseUrl="http://127.0.0.1/v1", modelId="fixture")}), "chat-completions"),
        ):
            self.write(value)
            with (patch.object(sys, "argv", ["inspect", "--connection", str(self.path)]),
                  patch.object(analysis, "AnalysisServer") as server, redirect_stdout(io.StringIO())):
                analysis.main()
                self.assertEqual(server.call_args.args[2].metadata["transport"], protocol)
            with (patch.object(sys, "argv", ["review", "--connection", str(self.path)]),
                  patch.object(review, "Application"), patch.object(review, "Study"),
                  patch.object(review, "Server") as server, redirect_stdout(io.StringIO())):
                review.main()
                self.assertEqual(server.call_args.args[2].metadata["transport"], protocol)


if __name__ == "__main__":
    unittest.main()
