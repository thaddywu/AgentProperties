"""Credential-holding relay restricted to the selected model and protocol."""

from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import threading
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .compatible import NoRedirect
from .model_settings import request_headers, validate_settings


class ModelProxy:
    def __init__(self, directory, connection, *, protocol="responses", record=None):
        if protocol not in {"responses", "chat-completions", "messages"}:
            raise ValueError("Unsupported standard model protocol.")
        connection = validate_settings(connection)
        base, model = connection["baseUrl"], connection["modelId"]
        route = {"responses": "/responses", "chat-completions": "/chat/completions",
                 "messages": "/messages"}[protocol]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                address = urlsplit(self.path)
                paths = {"/v1" + route: route}
                if protocol == "messages":
                    paths["/v1/messages/count_tokens"] = "/messages/count_tokens"
                if (address.path not in paths or address.query not in {"", "beta=true"}
                        or address.scheme or address.netloc or address.fragment):
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 8_000_000:
                        raise ValueError()
                    body = self.rfile.read(length)
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or payload.get("model") != model:
                        raise ValueError()
                    if protocol == "chat-completions":
                        # Transport translation only: preserve every original message.
                        outgoing = dict(payload)
                        outgoing.pop("thinking", None)
                        if "max_tokens" in outgoing:
                            outgoing["max_completion_tokens"] = outgoing.pop(
                                "max_tokens"
                            )
                        if connection.get("reasoningEffort") is not None:
                            outgoing["reasoning_effort"] = connection["reasoningEffort"]
                        body = json.dumps(outgoing).encode()
                        if record is not None:
                            from policyweave.core.artifacts import save

                            directory = Path(record)
                            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                            save(
                                directory / (uuid.uuid4().hex + ".json"),
                                dict(
                                    original=payload,
                                    upstream=outgoing,
                                    messagesUnchanged=payload.get("messages")
                                    == outgoing.get("messages"),
                                ),
                            )
                except (ValueError, TypeError, AttributeError):
                    self.send_error(400)
                    return
                headers = request_headers(connection, protocol)
                if protocol == "messages":
                    configured = {name.lower() for name in connection.get("headers", {})}
                    for header in ("anthropic-version", "anthropic-beta"):
                        value = self.headers.get(header)
                        if value is not None:
                            if len(value) > 4096 or any(c in value for c in "\r\n"):
                                self.send_error(400)
                                return
                            if header not in configured:
                                headers[header] = value
                endpoint = base + paths[address.path]
                if address.query:
                    endpoint += "?" + address.query
                try:
                    response = build_opener(NoRedirect()).open(
                        Request(endpoint, data=body, headers=headers), timeout=600
                    )
                except HTTPError as error:
                    # Arbitrary upstream error bodies may echo credentials.
                    error.close()
                    self.send_error(error.code if 400 <= error.code < 600 else 502,
                                    "Upstream model request failed.")
                    return
                except OSError:
                    self.send_error(502)
                    return
                self.send_response(response.status)
                self.send_header(
                    "Content-Type",
                    response.headers.get("Content-Type", "application/json"),
                )
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while chunk := response.read1(8192):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    response.close()

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        self.path = Path(directory) / "api.sock"
        self.server = Server(str(self.path), Handler)
        # Parent directory is private; the unprivileged container needs the socket.
        os.chmod(self.path, 0o666)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.path.unlink(missing_ok=True)
