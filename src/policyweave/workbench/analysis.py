"""Read-only log viewer and optional analysis model; never an app/agent runner."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
import shutil
import threading
import uuid
from urllib.parse import urlsplit, parse_qs

from policyweave.analysis.timeline import Timeline, decode_trajectory
from policyweave.analysis.call_analysis import analyze_call, call_questions
from policyweave.analysis.log_query import LogQuerySession, project
from policyweave.core.artifacts import save, artifact_text
from policyweave.core.policy import fingerprint
from policyweave._paths import state_directory
from .server import Handler, Server

MAX_BYTES = 64 * 1024 * 1024


class AnalysisServer(Server):
    def __init__(self, address, trajectory=None, generate=None, query_directory=None):
        timeline = Timeline(trajectory) if trajectory is not None else None
        super().__init__(address, None, generate)
        self.RequestHandlerClass = AnalysisHandler
        self.timeline = timeline
        self.documents = {}
        self.listed_documents = set()
        self.plans = {}
        self.gate_links = {}
        self.model_inputs = {}
        self.analysis_jobs = {}
        self.data_lock = threading.Lock()
        self.query_directory = Path(query_directory) if query_directory else None

    def document(self, identifier=None):
        if identifier is None:
            return self.timeline
        if not isinstance(identifier, str) or identifier not in self.documents:
            return (
                self.timeline
                if self.timeline is not None and identifier == self.timeline.identity
                else None
            )
        path, timeline = self.documents[identifier]
        value = decode_trajectory(artifact_text(path.parent, path.name, max_bytes=MAX_BYTES))
        if fingerprint(value) != identifier:
            raise ValueError("Registered evidence changed.")
        return timeline

    def register_file(self, path, timeline, *, listed=True):
        with self.data_lock:
            self.documents[timeline.identity] = Path(path), timeline
            if listed:
                self.listed_documents.add(timeline.identity)
            self.timeline = timeline

    def log_catalog(self):
        """List host-registered logs without exposing server filesystem paths."""
        rows = [
            dict(id=identifier, title=self.documents[identifier][1].describe()["title"])
            for identifier in sorted(self.listed_documents)
        ]
        if self.timeline is not None and self.timeline.identity not in self.documents:
            rows.append(
                dict(id=self.timeline.identity, title=self.timeline.describe()["title"])
            )
        return sorted(rows, key=lambda row: row["title"])

    def attach_gate(self, trajectory_id, event_id, gate_trajectory_id, gate_event_id):
        """Trusted host registration; client events never choose evidence files."""
        timeline, gate = self.document(trajectory_id), self.document(gate_trajectory_id)
        if timeline is None or gate is None:
            raise ValueError("Register both trajectories before linking gate evidence.")
        if gate.export()["format"] != "policyscope-trajectory":
            raise ValueError("Gate evidence needs a validated policy trajectory.")
        timeline.event(event_id)
        gate.event(gate_event_id)
        self.gate_links[trajectory_id, event_id] = gate_trajectory_id, gate_event_id

    def attach_model_input(self, trajectory_id, event_id, arguments):
        """Attach a host-recorded model request without changing the imported log."""
        timeline = self.document(trajectory_id)
        if timeline is None:
            raise ValueError("Register the trajectory before attaching model input.")
        timeline.event(event_id)
        if not isinstance(arguments, dict) or len(json.dumps(arguments)) > 1_000_000:
            raise ValueError("Expected bounded model input data.")
        self.model_inputs[trajectory_id, event_id] = deepcopy(arguments)

    def gate(self, timeline, event_id):
        link = self.gate_links.get((timeline.identity, event_id))
        if link:
            gate = self.document(link[0])
            if gate is None:
                raise ValueError("Linked gate evidence is unavailable.")
            return gate, link[1]
        return timeline.gate(event_id)

    def capabilities(self, timeline=None):
        timeline = timeline or self.timeline
        contract = (
            (timeline.export().get("analysis") or project(timeline)) if timeline else {}
        )
        return dict(
            queryAvailable=bool(shutil.which("souffle") and shutil.which("prlimit")),
            modelAvailable=self.generate is not None,
            queryExamples=contract.get("templates", []),
            queryEntities=contract.get("entities", {}),
        )


class AnalysisHandler(Handler):
    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "Local origin required."})
        route = urlsplit(self.path)
        params = parse_qs(route.query)
        if set(params) - {"trace"} or any(len(v) != 1 for v in params.values()):
            return self.reply(400, {"error": "Invalid trajectory selection."})
        if route.path.startswith("/api/analysis/jobs/"):
            identifier = route.path.removeprefix("/api/analysis/jobs/")
            with self.server.data_lock:
                job = deepcopy(self.server.analysis_jobs.get(identifier))
            if job is None:
                return self.reply(404, {"error": "Unknown analysis."})
            return self.reply(200, job)
        try:
            timeline = self.server.document(params.get("trace", [None])[0])
        except (ValueError, OSError):
            return self.reply(
                409, {"error": "Registered trajectory changed; reopen its evidence."}
            )
        if params.get("trace") and timeline is None:
            return self.reply(404, {"error": "Unknown trajectory."})
        if route.path == "/api/analysis/logs":
            return self.reply(200, dict(logs=self.server.log_catalog()))
        if route.path == "/api/analysis":
            return self.reply(
                200,
                dict(
                    token=self.server.token,
                    trajectory=timeline.describe() if timeline else None,
                    **self.server.capabilities(timeline),
                ),
            )
        if route.path == "/api/analysis/export" and timeline:
            return self.reply(200, timeline.export())
        assets = {
            "/": ("analysis.html", "text/html"),
            "/analysis.js": ("analysis.js", "text/javascript"),
            "/analysis.css": ("analysis.css", "text/css"),
            "/analysis-tokens.css": ("analysis-tokens.css", "text/css"),
            "/analysis-fonts.css": ("analysis-fonts.css", "text/css"),
        }
        for subset in ("latin", "latin-ext", "cyrillic", "cyrillic-ext", "vietnamese"):
            filename = f"geist-{subset}-wght-normal.woff2"
            assets["/" + filename] = filename, "font/woff2"
        if route.path not in assets:
            return self.reply(404, {"error": "Not found."})
        name, mime = assets[route.path]
        self.reply(200, (Path(__file__).parent / "static" / name).read_bytes(), mime)

    def do_POST(self):
        if not self.local() or not secrets.compare_digest(
            self.headers.get("X-Study-Token", ""), self.server.token
        ):
            return self.reply(403, {"error": "Local session token required."})
        if self.headers.get("Content-Type") != "application/json":
            return self.reply(415, {"error": "JSON required."})
        operation = self.path.removeprefix("/api/analysis/")
        if self.path != "/api/analysis/" + operation or operation not in {
            "import",
            "event",
            "query",
            "translate",
            "answer",
            "inspect",
            "explain",
        }:
            return self.reply(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = MAX_BYTES if operation == "import" else 200_000
            if not 0 < length <= limit or self.headers.get("Transfer-Encoding"):
                return self.reply(413, {"error": "Request exceeds the size limit."})
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Expected object.")
        except (ValueError, UnicodeError, RecursionError):
            return self.reply(400, {"error": "Invalid JSON request."})
        if operation in {"query", "translate", "answer", "explain"}:
            return self.analysis(operation, value)
        if operation == "inspect":
            return self.inspect(value)
        if not self.server.data_lock.acquire(blocking=False):
            return self.reply(409, {"error": "Another import is running."})
        try:
            if operation == "import":
                if set(value) not in ({"trajectory"}, {"text"}):
                    raise ValueError("Expected trajectory data only.")
                timeline = Timeline(decode_trajectory(value["text"]) if "text" in value else value["trajectory"])
                self.server.timeline = timeline
                result = timeline.describe()
            else:
                timeline = self.server.document(value.get("trajectoryId"))
                if timeline is None:
                    return self.reply(
                        400 if self.server.timeline is None else 409,
                        {"error": "Open the selected trajectory again."},
                    )
                if value.get("trajectoryId") != timeline.identity:
                    return self.reply(
                        409, {"error": "Trajectory changed; reload the view."}
                    )
                if set(value) != {"trajectoryId", "eventId"}:
                    raise ValueError("Unknown request fields.")
                result = timeline.event(value["eventId"])
            gate = self.server.gate(timeline, value["eventId"]) if operation == "event" else None
            enforcement = {
                key: item for key, item in gate[0].event(gate[1])["data"].items()
                if key in {"decision", "outcome", "effectCalled"}
            } if gate else None
            decision = (enforcement or {}).get("decision")
            self.reply(
                200,
                dict(
                    trajectoryId=timeline.identity,
                    result=result,
                    callQuestions=call_questions(decision["allowed"]) if decision else [],
                    **(
                        dict(enforcement=enforcement)
                        if gate else {}
                    ),
                    **(
                        dict(
                            modelInput=deepcopy(
                                self.server.model_inputs[
                                    timeline.identity, value["eventId"]
                                ]
                            )
                        )
                        if operation == "event"
                        and (timeline.identity, value["eventId"])
                        in self.server.model_inputs
                        else {}
                    ),
                    **(
                        dict(capabilities=self.server.capabilities())
                        if operation == "import"
                        else {}
                    ),
                ),
            )
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            self.reply(
                400, {"error": "Invalid trajectory. The selected log was preserved."}
            )
        except Exception:
            self.reply(500, {"error": "Could not read this trajectory."})
        finally:
            self.server.data_lock.release()

    def inspect(self, value):
        from policyweave.analysis.inspection import inspect

        if set(value) != {"trajectoryId", "eventId", "phase", "derive"}:
            return self.reply(400, {"error": "Select an event and snapshot only."})
        if value["derive"] is True and not self.server.capabilities()["queryAvailable"]:
            return self.reply(
                409, {"error": "Computing IDB requires the native engine."}
            )
        if not self.server.model_lock.acquire(blocking=False):
            return self.reply(409, {"error": "Another query is running."})
        try:
            timeline = self.server.document(value["trajectoryId"])
            if timeline is None or timeline.identity != value["trajectoryId"]:
                return self.reply(
                    409, {"error": "Trajectory changed; reload the view."}
                )
            gate = self.server.gate(timeline, value["eventId"])
            result = inspect(
                timeline,
                value["eventId"],
                phase=value["phase"],
                derive=value["derive"],
                gate=gate,
            )
            return self.reply(200, dict(trajectoryId=timeline.identity, result=result))
        except (ValueError, TypeError, KeyError):
            return self.reply(400, {"error": "Invalid snapshot or changed evidence."})
        except Exception:
            return self.reply(500, {"error": "Could not inspect these relations."})
        finally:
            self.server.model_lock.release()

    def analysis(self, operation, value):
        background = operation == "explain" and value.get("background") is True
        if "background" in value:
            if not background or set(value) != {"trajectoryId", "eventId", "templateId", "background"}:
                return self.reply(400, {"error": "Select an event and predefined question only."})
            value = {key: item for key, item in value.items() if key != "background"}
        if (
            operation != "translate"
            and not self.server.capabilities()["queryAvailable"]
        ):
            return self.reply(
                409, {"error": "Read-only queries require the native engine."}
            )
        if not self.server.model_lock.acquire(blocking=False):
            if background:
                with self.server.data_lock:
                    for identifier, job in self.server.analysis_jobs.items():
                        if job["status"] == "running" and job["request"] == value:
                            return self.reply(202, dict(jobId=identifier))
            return self.reply(409, {"error": "Another query is running."})
        if background:
            identifier = uuid.uuid4().hex
            with self.server.data_lock:
                while len(self.server.analysis_jobs) >= 20:
                    del self.server.analysis_jobs[next(iter(self.server.analysis_jobs))]
                self.server.analysis_jobs[identifier] = dict(
                    status="running", phase="evidence", request=value,
                )
            threading.Thread(target=self.run_analysis, args=(operation, value, identifier), daemon=True).start()
            return self.reply(202, dict(jobId=identifier))
        return self.run_analysis(operation, value)

    def run_analysis(self, operation, value, job_id=None):
        attempts = []
        usage_start = len(getattr(self.server.generate, "usage", []))
        saved = {}

        def generate(stage, prompt):
            if job_id:
                with self.server.data_lock:
                    self.server.analysis_jobs[job_id]["phase"] = (
                        "explanation" if stage == "call-analysis-answer" else "queries"
                    )
            return self.server.generate(stage, prompt)

        def run():
            nonlocal saved
            timeline = self.server.document(value.get("trajectoryId"))
            if timeline is None or value.get("trajectoryId") != timeline.identity:
                return (409, {"error": "Trajectory changed; reload the view."})
            session = LogQuerySession(timeline)
            if operation == "explain" and set(value) == {"trajectoryId", "eventId", "templateId"}:
                gate = self.server.gate(timeline, value["eventId"])
                result = analyze_call(
                    timeline,
                    value["eventId"],
                    value["templateId"],
                    generate if self.server.generate is not None else None,
                    gate=gate,
                    record=attempts.append,
                )
            elif operation == "translate" and set(value) == {
                "trajectoryId",
                "templateId",
                "parameters",
            }:
                result = session.prepare(value["templateId"], value["parameters"])
            elif operation == "answer" and set(value) == {"trajectoryId", "planId"}:
                plan = self.server.plans.get(value["planId"])
                if plan is None:
                    raise ValueError("Translate this question again.")
                result = session.answer(plan)
            elif operation == "query" and set(value) == {"trajectoryId", "query"}:
                result = session.query(value["query"])
            else:
                raise ValueError("Unknown query fields.")
            if operation == "translate" and result["status"] == "ready":
                identifier = uuid.uuid4().hex
                self.server.plans[identifier] = result
                if len(self.server.plans) > 100:
                    del self.server.plans[next(iter(self.server.plans))]
                result = dict(result, planId=identifier)
            saved = dict(result=result)
            return 200, dict(trajectoryId=timeline.identity, result=result)

        try:
            status, response = run()
        except (ValueError, TypeError, KeyError, OverflowError):
            saved = dict(error="Invalid read-only query or analysis contract.")
            status, response = (
                400,
                {
                    "error": "Query is outside the declared schema, bounded fact limit or supported read-only language."
                },
            )
        except Exception:
            saved = dict(error="Analysis failed; no successful answer was recorded.")
            status, response = 500, {"error": saved["error"]}
        finally:
            try:
                if self.server.query_directory:
                    self.server.query_directory.mkdir(
                        parents=True, exist_ok=True, mode=0o700
                    )
                    save(
                        self.server.query_directory / (uuid.uuid4().hex + ".json"),
                        dict(
                            request=value,
                            attempts=attempts,
                            **saved,
                            usage=getattr(self.server.generate, "usage", [])[
                                usage_start:
                            ],
                        ),
                    )
            except Exception:
                status, response = 500, {"error": "Could not retain query evidence."}
            finally:
                self.server.model_lock.release()
        if job_id:
            with self.server.data_lock:
                self.server.analysis_jobs[job_id].update(
                    status="completed" if status == 200 else "failed",
                    response=response,
                )
        else:
            self.reply(status, response)


def main():
    parser = argparse.ArgumentParser(
        description="Open the read-only trajectory viewer."
    )
    parser.add_argument("trajectory", nargs="?", type=Path)
    parser.add_argument("--traj", type=Path, help="Trajectory JSON to open")
    parser.add_argument("--port", type=int, default=5191)
    parser.add_argument(
        "--rules", type=Path, help="Historical analysis .dl for execution observations"
    )
    parser.add_argument(
        "--connection",
        type=Path,
        help="Optional analysis model; never connects to recorded agents",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=state_directory() / "analysis-queries",
        help="Private query evidence directory",
    )
    args = parser.parse_args()
    if args.traj:
        if args.trajectory:
            parser.error("Choose a positional trajectory or --traj.")
        args.trajectory = args.traj
    trajectory = None
    if args.trajectory:
        if not args.trajectory.is_file() or args.trajectory.stat().st_size > MAX_BYTES:
            parser.error("Expected a trajectory JSON file of at most 64 MiB.")
        trajectory = decode_trajectory(args.trajectory.read_text())
        if args.rules:
            from policyweave.analysis.execution import execution_analysis

            trajectory = execution_analysis(trajectory, rules=args.rules.read_text())
    elif args.rules:
        parser.error("--rules requires a trajectory file.")
    generate = None
    if args.connection:
        from policyweave.adapters.compatible import Connection
        from policyweave.adapters.model_settings import load_connection

        generate = Connection(load_connection(args.connection))
    server = AnalysisServer(("127.0.0.1", args.port), trajectory, generate, args.data)
    print(f"Trajectory viewer: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
