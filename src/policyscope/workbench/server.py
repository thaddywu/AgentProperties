"""Local single-study HTTP composition root. Never accepts executable connectors or model settings over HTTP."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import uuid

from policyscope.policy_adder import TranslationFailure, translate
from .study import now
from .cases import run_cases


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, study, generate=None, port_jobs=None):
        if address[0] != "127.0.0.1":
            raise ValueError("The local evaluation server binds only to loopback.")
        super().__init__(address, Handler)
        self.study, self.generate = study, generate
        self.port_jobs = port_jobs
        self.token = secrets.token_urlsafe(32)
        self.model_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log policy documents, response bodies or credentials.

    def local(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        return self.headers.get("Host") in allowed and self.headers.get(
            "Origin", f"http://127.0.0.1:{port}"
        ) in {"http://" + host for host in allowed}

    def reply(self, status, body, mime="application/json"):
        raw = (
            json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            if mime == "application/json"
            else body
        )
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "Local origin required."})
        if self.path == "/api/study":
            return self.reply(
                200,
                dict(
                    study=self.server.study.export(),
                    token=self.server.token,
                    modelAvailable=self.server.generate is not None
                    and self.server.port_jobs is None,
                    repositoryJob=self.server.port_jobs.status()
                    if self.server.port_jobs
                    else None,
                    studentReview=hasattr(self.server.study, "submission"),
                    setupFields=self.server.study.application.setup_fields,
                    runner=getattr(self.server.study.application, "runner_info", {}),
                    summary=self.server.study.summary(),
                ),
            )
        if self.path == "/api/port-job" and self.server.port_jobs:
            return self.reply(200, self.server.port_jobs.status())
        if self.path == "/api/review" and hasattr(self.server.study, "submission"):
            return self.reply(200, self.server.study.submission())
        if self.path == "/api/export":
            return self.reply(
                200,
                dict(
                    study=self.server.study.export(),
                    summary=self.server.study.summary(),
                ),
            )
        assets = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if self.path not in assets:
            return self.reply(404, {"error": "Not found."})
        file, mime = assets[self.path]
        self.reply(200, (Path(__file__).parent / "static" / file).read_bytes(), mime)

    def do_POST(self):
        if not self.local() or not secrets.compare_digest(
            self.headers.get("X-Study-Token", ""), self.server.token
        ):
            return self.reply(403, {"error": "Local study token required."})
        if self.headers.get("Content-Type") != "application/json":
            return self.reply(415, {"error": "JSON required."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 200_000:
                raise ValueError("Request body exceeds the size limit.")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object.")
            study = self.server.study
            if self.path == "/api/port-job":
                if self.server.port_jobs is None or set(value) != {"stage"}:
                    raise ValueError("No repository translation configured.")
                result = self.server.port_jobs.start(value["stage"])
            elif self.path == "/api/judgment":
                study.judge(
                    value["reviewId"], value["requirementId"], value["judgment"]
                )
                result = {"saved": True}
            elif self.path == "/api/scenario":
                result = study.add_scenario(value)
            elif self.path == "/api/run-cases":
                result = run_cases(study, value)
            elif self.path == "/api/run":
                result = study.run_pair(
                    value["scenarioId"], value.get("repetitions", 1)
                )
            elif self.path == "/api/event-judgment":
                study.judge_event(
                    value["pairId"], value["mode"], value["eventId"], value["judgment"]
                )
                result = {"saved": True}
            elif self.path == "/api/run-judgment":
                study.judge_run(value["pairId"], value["mode"], value["judgment"])
                result = {"saved": True}
            elif self.path == "/api/translate":
                if self.server.generate is None or self.server.port_jobs is not None:
                    raise ValueError("No model connection is configured.")
                if not self.server.model_lock.acquire(blocking=False):
                    raise ValueError("Another translation is running.")
                records = []
                usage_start = len(getattr(self.server.generate, "usage", []))
                model_metadata = getattr(self.server.generate, "metadata", {})
                try:
                    review = translate(
                        value["text"],
                        study.application.binding,
                        self.server.generate,
                        name=value.get("name", "policy.txt"),
                        documents=study.application.documents,
                        record=records.append,
                        model_metadata=model_metadata,
                    )
                    with study.lock:
                        # Raw prompts/responses stay in the private study directory, out of normal UI responses.
                        path = study.directory / (
                            "translation-" + review["id"] + ".json"
                        )
                        with path.open("w") as stream:
                            path.chmod(0o600)
                            json.dump(records, stream, ensure_ascii=False, indent=2)
                        study.add_review(
                            review,
                            getattr(self.server.generate, "usage", [])[usage_start:],
                        )
                    result = review
                except TranslationFailure as error:
                    with study.lock:
                        failure_id = uuid.uuid4().hex
                        path = study.directory / (
                            "translation-failure-" + failure_id + ".json"
                        )
                        with path.open("x") as stream:
                            path.chmod(0o600)
                            json.dump(
                                error.attempts, stream, ensure_ascii=False, indent=2
                            )
                        study.data["failures"].append(
                            dict(
                                id=failure_id,
                                recordFile=path.name,
                                createdAt=now(),
                                error=str(error),
                                attempts=[
                                    {
                                        k: v
                                        for k, v in attempt.items()
                                        if k not in ("prompt", "response")
                                    }
                                    for attempt in error.attempts
                                ],
                                model=model_metadata,
                                usage=getattr(self.server.generate, "usage", [])[
                                    usage_start:
                                ],
                            )
                        )
                        study.save()
                    raise ValueError(str(error)) from None
                finally:
                    self.server.model_lock.release()
            elif self.path == "/api/query":
                pair = next(
                    p for p in study.export()["pairs"] if p["id"] == value["pairId"]
                )
                event = next(
                    e
                    for e in pair["runs"][value["mode"]]["events"]
                    if e["id"] == value["eventId"]
                )
                result = study.application.inspect(event["snapshot"], value["question"])
            else:
                return self.reply(404, {"error": "Not found."})
            self.reply(200, result)
        except (ValueError, TypeError, KeyError, StopIteration):
            # Domain failures can contain untrusted text; send only safe API messages.
            self.reply(
                400,
                {
                    "error": "The request could not be completed. Check required fields, model configuration, or the saved failure record."
                },
            )
        except Exception:
            self.reply(
                500, {"error": "Operation failed; no successful result was recorded."}
            )
