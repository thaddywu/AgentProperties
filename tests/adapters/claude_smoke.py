"""Real Claude Code + Docker, with a deterministic local Messages fixture only.

No provider account, live model requests or application-completion claim.
Run explicitly; normal offline tests require neither Docker nor a coding CLI.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from policyweave.policy_adder.codex import CodexPort


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="policy-portin:batch-v1")
    args = parser.parse_args()
    requests = []
    exchanges = []
    model = "claude-sonnet-4-6"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.headers["x-api-key"] == "synthetic-host-key"
            assert payload["model"] == model
            requests.append(self.path)
            if self.path.split("?", 1)[0] == "/v1/messages/count_tokens":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"input_tokens":10}')
                return
            assert self.path.split("?", 1)[0] == "/v1/messages"
            assert payload["stream"] is True
            main_call = any(tool.get("name") == "Bash" for tool in payload.get("tools", []))
            index = len(exchanges)
            if main_call:
                exchanges.append(payload)
            if main_call and index < 2:
                name = "input.json" if index == 0 else "result.json"
                block = dict(type="tool_use", id="toolu_fixture" + str(index), name="Bash", input={})
                delta = dict(type="input_json_delta", partial_json=json.dumps(dict(
                    command="printf '%s' '{\"ok\":true}' > /work/" + name,
                    description="Write synthetic fixture output")))
                reason = "tool_use"
            else:
                block = dict(type="text", text="")
                delta = dict(type="text_delta", text="Synthetic output saved.")
                reason = "end_turn"
            events = [
                dict(type="message_start", message=dict(
                    id="msg_fixture" + str(index), type="message", role="assistant", model=model,
                    content=[], stop_reason=None, stop_sequence=None,
                    usage=dict(input_tokens=10, output_tokens=0))),
                dict(type="content_block_start", index=0, content_block=block),
                dict(type="content_block_delta", index=0, delta=delta),
                dict(type="content_block_stop", index=0),
                dict(type="message_delta", delta=dict(stop_reason=reason, stop_sequence=None),
                     usage=dict(output_tokens=10)),
                dict(type="message_stop"),
            ]
            raw = "".join("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n"
                          for event in events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="policy-claude-smoke-") as directory:
            root = Path(directory)
            (root / "input.json").write_text('{"frozen":true}')
            (root / "AGENTS.md").write_text("Write only result.json. Input is immutable. No subagents.\n")
            port = CodexPort(root, dict(protocol="messages", modelId=model,
                baseUrl=f"http://127.0.0.1:{server.server_port}/v1", apiKey="synthetic-host-key"),
                image=args.image, timeout=45)
            # The fixture needs no retained Docker image tag.
            with patch.object(port, "pin_image"):
                code = port.session(root, "Read input.json, then write result.json.", "fixture", ("input.json",))
            if code or not (root / "result.json").is_file():
                # Fixture-only logs contain no real provider credentials.
                detail = (root / "fixture.stderr").read_text()[-2000:]
                detail += (root / "fixture.jsonl").read_text()[-4000:]
                raise AssertionError("Claude fixture session failed: " + str(code) + "\n" + detail)
            assert (root / "input.json").read_text() == '{"frozen":true}'
            assert json.loads((root / "result.json").read_text()) == {"ok": True}
            assert (root / "fixture-final.txt").is_file()
            assert "synthetic-host-key" not in (root / "fixture.jsonl").read_text()
            assert len(exchanges) == 3
            results = [block for exchange in exchanges for message in exchange["messages"] if isinstance(message.get("content"), list)
                       for block in message["content"] if block.get("type") == "tool_result"]
            assert any("read-only" in json.dumps(result).lower() or
                       "permission denied" in json.dumps(result).lower()
                       for result in results), "Protected file write was not refused: " + json.dumps(results)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print("Real Claude Code completed a fixture tool loop in a network-isolated container; frozen input, output and host-only credential checks passed.")


if __name__ == "__main__":
    main()
