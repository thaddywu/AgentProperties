"""Read-only log viewer and optional analysis model; never an app/agent runner."""

import argparse
import json
from pathlib import Path
import secrets
import shutil
import threading
import uuid
from urllib.parse import urlsplit, parse_qs

from policyscope.analysis.timeline import Timeline
from policyscope.analysis.log_query import LogQuerySession
from policyscope.core.artifacts import save, artifact_text
from policyscope._paths import state_directory
from .server import Handler, Server

MAX_BYTES = 64 * 1024 * 1024


class AnalysisServer(Server):
    def __init__(self, address, trajectory=None, generate=None, query_directory=None):
        timeline = Timeline(trajectory) if trajectory is not None else None
        super().__init__(address, None, generate)
        self.RequestHandlerClass = AnalysisHandler
        self.timeline = timeline
        self.documents = {}
        self.data_lock = threading.Lock()
        self.query_directory = Path(query_directory) if query_directory else None

    def document(self, identifier=None):
        if identifier is None:
            return self.timeline
        if self.timeline is not None and identifier == self.timeline.identity:
            return self.timeline
        if not isinstance(identifier, str) or identifier not in self.documents:
            return None
        path = self.documents[identifier]
        value = Timeline(
            json.loads(artifact_text(path.parent, path.name, max_bytes=MAX_BYTES))
        )
        if value.identity != identifier:
            raise ValueError("Registered evidence changed.")
        return value

    def register_file(self, path, timeline):
        with self.data_lock:
            self.documents[timeline.identity] = Path(path)
            self.timeline = timeline

    def capabilities(self, timeline=None):
        timeline = timeline or self.timeline
        return dict(
            queryAvailable=bool(shutil.which("souffle") and shutil.which("prlimit")),
            modelAvailable=self.generate is not None,
            queryExamples=timeline.export().get("analysis", {}).get("templates", [])
            if timeline
            else [],
        )


class AnalysisHandler(Handler):
    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "Local origin required."})
        route = urlsplit(self.path)
        params = parse_qs(route.query)
        if set(params) - {"trace"} or any(len(v) != 1 for v in params.values()):
            return self.reply(400, {"error": "Invalid trajectory selection."})
        try:
            timeline = self.server.document(params.get("trace", [None])[0])
        except (ValueError, OSError):
            return self.reply(
                409, {"error": "Registered trajectory changed; reopen its evidence."}
            )
        if params.get("trace") and timeline is None:
            return self.reply(404, {"error": "Unknown trajectory."})
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
        }
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
            "ask",
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
        if operation in {"query", "ask"}:
            return self.analysis(operation, value)
        if not self.server.data_lock.acquire(blocking=False):
            return self.reply(409, {"error": "Another import is running."})
        try:
            if operation == "import":
                if set(value) != {"trajectory"}:
                    raise ValueError("Expected trajectory data only.")
                timeline = Timeline(value["trajectory"])
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
            self.reply(
                200,
                dict(
                    trajectoryId=timeline.identity,
                    result=result,
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

    def analysis(self, operation, value):
        if not self.server.capabilities()["queryAvailable"]:
            return self.reply(
                409, {"error": "Read-only queries require the native engine."}
            )
        if not self.server.model_lock.acquire(blocking=False):
            return self.reply(409, {"error": "Another query is running."})
        attempts = []
        usage_start = len(getattr(self.server.generate, "usage", []))
        saved = {}
        try:
            timeline = self.server.document(value.get("trajectoryId"))
            if timeline is None or value.get("trajectoryId") != timeline.identity:
                return self.reply(
                    409, {"error": "Trajectory changed; reload the view."}
                )
            field = "question" if operation == "ask" else "query"
            if set(value) != {"trajectoryId", field}:
                raise ValueError("Unknown query fields.")
            session = LogQuerySession(timeline)
            if operation == "ask":
                if self.server.generate is None:
                    return self.reply(
                        409,
                        {
                            "error": "Natural-language analysis needs an optional model connection."
                        },
                    )
                result = session.ask(
                    value[field], self.server.generate, record=attempts.append
                )
            else:
                result = session.query(value[field])
            saved = dict(result=result)
            self.reply(200, dict(trajectoryId=timeline.identity, result=result))
        except (ValueError, TypeError, KeyError, OverflowError):
            saved = dict(error="Invalid read-only query or analysis contract.")
            self.reply(
                400,
                {
                    "error": "Query is outside the declared schema, bounded fact limit or supported read-only language."
                },
            )
        except Exception:
            saved = dict(error="Analysis failed; no successful answer was recorded.")
            self.reply(500, {"error": saved["error"]})
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
            finally:
                self.server.model_lock.release()


def main():
    parser = argparse.ArgumentParser(
        description="Open the read-only trajectory viewer."
    )
    parser.add_argument("trajectory", nargs="?", type=Path)
    parser.add_argument("--port", type=int, default=5191)
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
    trajectory = None
    if args.trajectory:
        if not args.trajectory.is_file() or args.trajectory.stat().st_size > MAX_BYTES:
            parser.error("Expected a trajectory JSON file of at most 64 MiB.")
        trajectory = json.loads(args.trajectory.read_text())
    generate = None
    if args.connection:
        from policyscope.adapters.compatible import Connection

        generate = Connection(json.loads(args.connection.read_text()))
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
