"""One offline model contract for Chat Completions and native Messages."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import yaml
from unittest.mock import patch

from policyweave.adapters.compatible import Connection
from policyweave.adapters.coding import CodingAgent
from policyweave.adapters.messages import structured_schema
from policyweave.adapters.model_proxy import ModelProxy
from policyweave.policy_adder.student import load_connection
from policyweave.policy_adder.codex import CodexPort


class ModelFixture:
    def __enter__(self):
        fixture = self
        self.requests = []
        self.status = 200
        self.headers = {}
        self.reply = None

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.requests.append(dict(path=self.path, headers=dict(self.headers), payload=payload))
                if fixture.reply is None:
                    if self.path.startswith("/v1/messages"):
                        value = dict(type="message", role="assistant", stop_reason="end_turn",
                                     content=[dict(type="text", text='{"ok":true}')],
                                     usage=dict(input_tokens=4, output_tokens=3))
                    else:
                        value = dict(choices=[dict(finish_reason="stop", message=dict(content='{"ok":true}'))],
                                     usage=dict(prompt_tokens=4, completion_tokens=3, total_tokens=7))
                    body = json.dumps(value).encode()
                else:
                    body = fixture.reply
                self.send_response(fixture.status)
                self.send_header("Content-Type", fixture.headers.get("Content-Type", "application/json"))
                for name, value in fixture.headers.items():
                    if name != "Content-Type":
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ModelConformanceTests(unittest.TestCase):
    def test_same_json_usage_metadata_and_structured_contract(self):
        schema = dict(type="object", properties=dict(ok=dict(type="boolean")),
                      required=["ok"], additionalProperties=False)
        response_format = dict(type="json_schema", json_schema=dict(name="fixture", strict=True, schema=schema))
        with ModelFixture() as fixture:
            for protocol in ("chat-completions", "messages"):
                with self.subTest(protocol=protocol):
                    settings = dict(protocol=protocol, baseUrl=fixture.base, modelId="fixture-model",
                                    apiKey="synthetic-host-key", responseFormat=response_format,
                                    reasoningEffort="medium", headers={"X-Fixture": "configured"})
                    before = deepcopy(settings)
                    model = Connection(settings)
                    self.assertEqual(json.loads(model("analysis", "untrusted document")), {"ok": True})
                    self.assertEqual(settings, before)
                    self.assertEqual(model.metadata["transport"], protocol)
                    usage = model.usage[0]
                    self.assertEqual([usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")], [4, 3, 7])
                    self.assertNotIn("synthetic-host-key", json.dumps([model.metadata, model.usage]))
                    request = fixture.requests[-1]
                    headers = {k.lower(): v for k, v in request["headers"].items()}
                    self.assertEqual(headers["x-fixture"], "configured")
                    if protocol == "messages":
                        self.assertEqual(request["path"], "/v1/messages")
                        self.assertEqual(headers["x-api-key"], "synthetic-host-key")
                        self.assertIn("anthropic-version", headers)
                        self.assertNotIn("authorization", headers)
                        self.assertEqual(request["payload"]["output_config"]["format"]["schema"], schema)
                        self.assertEqual(request["payload"]["output_config"]["effort"], "medium")
                        self.assertEqual(request["payload"]["messages"], [dict(role="user", content="untrusted document")])
                    else:
                        self.assertEqual(request["path"], "/v1/chat/completions")
                        self.assertEqual(headers["authorization"], "Bearer synthetic-host-key")

    def test_truncation_refusal_tool_calls_and_empty_text_fail_without_usage(self):
        with ModelFixture() as fixture:
            for reason, content in (
                ("max_tokens", [dict(type="text", text='{"partial":')]),
                ("refusal", [dict(type="text", text="refused")]),
                ("tool_use", [dict(type="tool_use", name="Bash", input={})]),
                ("end_turn", [dict(type="thinking", thinking="private")]),
            ):
                fixture.reply = json.dumps(dict(type="message", stop_reason=reason, content=content)).encode()
                model = Connection(dict(protocol="messages", baseUrl=fixture.base, modelId="fixture"))
                with self.assertRaisesRegex(RuntimeError, "invalid response"):
                    model("test", "data")
                self.assertEqual(model.usage, [])

    def test_credentials_do_not_follow_redirects_or_appear_in_errors(self):
        with ModelFixture() as fixture:
            fixture.status = 307
            fixture.headers["Location"] = fixture.base + "/redirect-target"
            fixture.reply = b"synthetic-host-key"
            for protocol in ("messages", "chat-completions"):
                model = Connection(dict(protocol=protocol, baseUrl=fixture.base, modelId="fixture", apiKey="synthetic-host-key"))
                with self.assertRaises(RuntimeError) as error:
                    model("test", "data")
                self.assertNotIn("synthetic-host-key", str(error.exception))
            self.assertEqual(len(fixture.requests), 2)
            self.assertTrue(all("redirect-target" not in row["path"] for row in fixture.requests))

    def test_schema_projection_preserves_host_schema_and_explains_bounds(self):
        schema = dict(type="object", additionalProperties=False, properties=dict(
            items=dict(type="array", minItems=2, maxItems=8, items=dict(type="string", minLength=2))))
        before = deepcopy(schema)
        projected = structured_schema(schema)
        self.assertEqual(schema, before)
        self.assertNotIn("maxItems", projected["properties"]["items"])
        self.assertEqual(projected["properties"]["items"]["minItems"], 1)
        self.assertIn('"maxItems": 8', projected["properties"]["items"]["description"])

    def test_messages_defaults_and_explicit_model_and_effort_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connection.yaml"
            path.write_text(yaml.safe_dump(dict(anthropic=dict(apiKey="synthetic", modelId="fixture-model",
                                                              reasoningEffort=None))))
            settings = load_connection(path)
            self.assertEqual(settings["baseUrl"], "https://api.anthropic.com/v1")
            self.assertIsNone(settings["reasoningEffort"])
            self.assertEqual(settings["modelId"], "fixture-model")
            path.write_text(yaml.safe_dump(dict(anthropic=dict(apiKey="synthetic"))))
            settings = load_connection(path)
            self.assertEqual(settings["modelId"], "claude-opus-5-5")
            self.assertEqual(settings["reasoningEffort"], "medium")

    def test_both_protocols_reject_unsafe_connections_before_network(self):
        for protocol in ("messages", "chat-completions"):
            for extra in (dict(baseUrl="http://example.invalid/v1"),
                          dict(apiKey="synthetic\r\ninjection"),
                          dict(headers={"Authorization": "synthetic"}),
                          dict(headers={"X-Test": "value\nsecond"})):
                with self.subTest(protocol=protocol, fields=list(extra)):
                    with self.assertRaises(ValueError):
                        Connection(dict(dict(protocol=protocol, baseUrl="https://example.invalid/v1", modelId="fixture"), **extra))


def proxy_request(proxy, path, payload, headers=None):
    connection = http.client.HTTPConnection("localhost", timeout=5)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(5)
    connection.sock.connect(str(proxy.path))
    try:
        connection.request("POST", path, json.dumps(payload), headers or {})
        response = connection.getresponse()
        return response.status, response.read(), response.getheader("Content-Type")
    finally:
        connection.close()


class RelayTests(unittest.TestCase):
    def test_messages_stream_and_token_count_preserve_payload_and_hold_key(self):
        with ModelFixture() as fixture, tempfile.TemporaryDirectory() as directory:
            fixture.headers["Content-Type"] = "text/event-stream"
            fixture.reply = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
            settings = dict(protocol="messages", baseUrl=fixture.base, modelId="fixture", apiKey="synthetic-host-key")
            with ModelProxy(directory, settings, protocol="messages") as proxy:
                payload = dict(model="fixture", stream=True, messages=[dict(role="user", content="data")])
                status, body, content_type = proxy_request(proxy, "/v1/messages?beta=true", payload,
                    {"X-Api-Key": "untrusted-container-key", "anthropic-beta": "fixture-beta"})
                self.assertEqual((status, body, content_type), (200, fixture.reply, "text/event-stream"))
                self.assertEqual(fixture.requests[-1]["payload"], payload)
                headers = {k.lower(): v for k, v in fixture.requests[-1]["headers"].items()}
                self.assertEqual(headers["x-api-key"], "synthetic-host-key")
                self.assertEqual(headers["anthropic-beta"], "fixture-beta")
                self.assertNotIn("untrusted-container-key", json.dumps(fixture.requests))
                self.assertEqual(proxy_request(proxy, "/v1/messages/count_tokens", dict(model="fixture"))[0], 200)
                count = len(fixture.requests)
                for path, value, expected in (
                    ("/v1/responses", payload, 404),
                    ("/v1/messages?destination=elsewhere", payload, 404),
                    ("/v1/messages", dict(model="other"), 400),
                    ("/v1/messages", [], 400),
                ):
                    self.assertEqual(proxy_request(proxy, path, value)[0], expected)
                self.assertEqual(len(fixture.requests), count)

    def test_relay_redacts_upstream_errors_and_does_not_follow_redirects(self):
        with ModelFixture() as fixture, tempfile.TemporaryDirectory() as directory:
            settings = dict(protocol="messages", baseUrl=fixture.base, modelId="fixture", apiKey="synthetic-host-key")
            with ModelProxy(directory, settings, protocol="messages") as proxy:
                for code in (401, 429, 307):
                    fixture.status = code
                    fixture.reply = b"synthetic-host-key"
                    fixture.headers["Location"] = fixture.base + "/redirect"
                    status, body, _ = proxy_request(proxy, "/v1/messages", dict(model="fixture"))
                    self.assertEqual(status, code if code != 307 else 502)
                    self.assertNotIn(b"synthetic-host-key", body)
            self.assertEqual(len(fixture.requests), 3)


class CodingContractTests(unittest.TestCase):
    def test_both_coders_keep_credentials_out_of_commands_and_mounts(self):
        with patch("policyweave.adapters.coding.shutil.which", return_value="/synthetic/coder"):
            for protocol in ("messages", "chat-completions"):
                coder = CodingAgent(dict(protocol=protocol, baseUrl="https://example.invalid/v1",
                                         modelId="fixture", apiKey="synthetic-host-key"))
                command = [*coder.arguments("stage"), *coder.environment(), *coder.mounts()]
                self.assertNotIn("synthetic-host-key", json.dumps(command))
                if protocol == "messages":
                    self.assertIn("--bare", command)
                    self.assertIn("--strict-mcp-config", command)
                    self.assertIn("--no-session-persistence", command)
                    self.assertIn("Read,Edit,Bash", command)

    def test_success_requires_complete_successful_terminal_result(self):
        with patch("policyweave.adapters.coding.shutil.which", return_value="/synthetic/coder"):
            coder = CodingAgent(dict(protocol="messages", baseUrl="https://example.invalid/v1", modelId="fixture"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = dict(type="result", subtype="success", is_error=False, result="saved")
            for rows, expected in (([result], 0), ([], 1),
                                   ([dict(result, is_error=True)], 1),
                                   ([dict(result, subtype="error_max_turns")], 1),
                                   ([result, result], 1)):
                (root / "stage.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
                self.assertEqual(coder.finish(root, "stage", 0), expected)
            self.assertEqual((root / "stage-final.txt").read_text(), "saved")

    def test_claude_session_reuses_docker_freezes_and_kills_timed_out_container(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.json").write_text("{}")
            (root / "AGENTS.md").write_text("Frozen stage instructions")
            port = CodexPort(root, dict(protocol="messages", baseUrl="https://example.invalid/v1",
                modelId="fixture", apiKey="synthetic-host-key", codingCommand=sys.executable))
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                self.assertIn("--network", command)
                self.assertEqual(command[command.index("--network") + 1], "none")
                self.assertIn("--read-only", command)
                self.assertTrue(any("target=/work/input.json,readonly" in item for item in command))
                self.assertTrue(any("target=/work/AGENTS.md,readonly" in item for item in command))
                self.assertNotIn("synthetic-host-key", json.dumps(command))
                kwargs["stdout"].write(json.dumps(dict(type="result", subtype="success", is_error=False, result="done")) + "\n")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(port, "pin_image"), patch("policyweave.policy_adder.codex.subprocess.run", side_effect=run):
                self.assertEqual(port.session(root, "data", "success", ("input.json",)), 0)
            self.assertEqual((root / "success-final.txt").read_text(), "done")
            timed_out = subprocess.TimeoutExpired("fixture", 1)
            with patch.object(port, "pin_image"), patch("policyweave.policy_adder.codex.subprocess.run",
                    side_effect=[timed_out, subprocess.CompletedProcess([], 0)]) as run:
                self.assertEqual(port.session(root, "data", "timeout", ("input.json",)), 124)
                self.assertEqual(run.call_args_list[-1].args[0][:3], ["docker", "rm", "-f"])


if __name__ == "__main__":
    unittest.main()
