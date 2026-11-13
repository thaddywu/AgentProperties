"""Local data-only trajectory viewer; no model connection or app runner."""

import argparse
import json
from pathlib import Path
import secrets

from policyscope.analysis.timeline import Timeline
from .server import Handler, Server

MAX_BYTES = 64 * 1024 * 1024


class AnalysisServer(Server):
    def __init__(self, address, trajectory=None):
        timeline = Timeline(trajectory) if trajectory is not None else None
        super().__init__(address, None)
        self.RequestHandlerClass = AnalysisHandler
        self.timeline = timeline


class AnalysisHandler(Handler):
    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "Local origin required."})
        timeline = self.server.timeline
        if self.path == "/api/analysis":
            return self.reply(
                200,
                dict(
                    token=self.server.token,
                    trajectory=timeline.describe() if timeline else None,
                ),
            )
        if self.path == "/api/analysis/export" and timeline:
            return self.reply(200, timeline.export())
        assets = {
            "/": ("analysis.html", "text/html"),
            "/analysis.js": ("analysis.js", "text/javascript"),
            "/analysis.css": ("analysis.css", "text/css"),
        }
        if self.path not in assets:
            return self.reply(404, {"error": "Not found."})
        name, mime = assets[self.path]
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
        if not self.server.model_lock.acquire(blocking=False):
            return self.reply(409, {"error": "Another import is running."})
        try:
            if operation == "import":
                if set(value) != {"trajectory"}:
                    raise ValueError("Expected trajectory data only.")
                timeline = Timeline(value["trajectory"])
                self.server.timeline = timeline
                result = timeline.describe()
            else:
                timeline = self.server.timeline
                if timeline is None:
                    return self.reply(400, {"error": "Open a trajectory first."})
                if value.get("trajectoryId") != timeline.identity:
                    return self.reply(
                        409, {"error": "Trajectory changed; reload the view."}
                    )
                if set(value) != {"trajectoryId", "eventId"}:
                    raise ValueError("Unknown request fields.")
                result = timeline.event(value["eventId"])
            self.reply(200, dict(trajectoryId=timeline.identity, result=result))
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            self.reply(
                400, {"error": "Invalid trajectory. The selected log was preserved."}
            )
        except Exception:
            self.reply(500, {"error": "Could not read this trajectory."})
        finally:
            self.server.model_lock.release()


def main():
    parser = argparse.ArgumentParser(
        description="Open the read-only trajectory viewer."
    )
    parser.add_argument("trajectory", nargs="?", type=Path)
    parser.add_argument("--port", type=int, default=5191)
    args = parser.parse_args()
    trajectory = None
    if args.trajectory:
        if not args.trajectory.is_file() or args.trajectory.stat().st_size > MAX_BYTES:
            parser.error("Expected a trajectory JSON file of at most 64 MiB.")
        trajectory = json.loads(args.trajectory.read_text())
    server = AnalysisServer(("127.0.0.1", args.port), trajectory)
    print(f"Trajectory viewer: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
