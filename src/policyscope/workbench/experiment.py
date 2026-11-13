"""Trusted execution composition, separate from the data-only post-mortem server."""

from copy import deepcopy
import json
from pathlib import Path
import secrets
import threading
import uuid

from policyscope.analysis.timeline import Timeline
from policyscope.core.artifacts import artifact_text, save
from policyscope.core.policy import fingerprint
from .server import Handler, Server


class Experiment:
    def __init__(self, cases, execute, directory, viewer):
        self.cases = {case["id"]: deepcopy(case) for case in cases}
        self.execute = execute
        self.directory = Path(directory).resolve()
        self.viewer = viewer
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()
        self.job = None
        self.records = {}

    def register(self, rows, root, job="imported"):
        root = Path(root).resolve()
        additions = {}
        for row in rows:
            if row["caseId"] not in self.cases or row["mode"] not in {
                "baseline",
                "protected",
            }:
                raise ValueError("Unknown case artifact.")
            relative = row["timeline"]
            Timeline(
                json.loads(artifact_text(root, relative, max_bytes=64 * 1024 * 1024))
            )
            identifier = fingerprint(
                dict(
                    case=row["caseId"],
                    mode=row["mode"],
                    repetition=row["repetition"],
                    job=job,
                )
            )[:24]
            additions[identifier] = dict(
                row, id=identifier, path=str(root / relative), job=job
            )
        with self.lock:
            # Keep complete histories on disk; the UI selects the newest batch.
            cases = {r["caseId"] for r in additions.values()}
            self.records = {
                k: v for k, v in self.records.items() if v["caseId"] not in cases
            }
            self.records.update(additions)

    def state(self):
        with self.lock:
            return deepcopy(
                dict(
                    cases=list(self.cases.values()),
                    job=self.job,
                    records=[
                        {k: v for k, v in row.items() if k not in {"path", "timeline"}}
                        for row in self.records.values()
                    ],
                )
            )

    def start(self, case_id, repetitions):
        if (
            not isinstance(case_id, str)
            or case_id not in self.cases
            or type(repetitions) is not int
            or not 1 <= repetitions <= 5
        ):
            raise ValueError("Choose a case and 1–5 repetitions.")
        with self.lock:
            if self.job and self.job["status"] == "running":
                raise ValueError("Another case is running.")
            identifier = uuid.uuid4().hex
            self.job = dict(
                id=identifier, caseId=case_id, status="running", repetitions=repetitions
            )
        destination = self.directory / identifier
        destination.mkdir(mode=0o700)
        save(destination / "case.json", self.cases[case_id])

        def run():
            try:
                rows = self.execute(
                    deepcopy(self.cases[case_id]), repetitions, destination
                )
                self.register(rows, destination, identifier)
                status = dict(
                    id=identifier,
                    caseId=case_id,
                    status="completed",
                    repetitions=repetitions,
                )
            except Exception as error:
                status = dict(
                    id=identifier,
                    caseId=case_id,
                    status="failed",
                    errorType=type(error).__name__,
                )
            save(destination / "job.json", status)
            with self.lock:
                self.job = status

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return identifier

    def inspect(self, identifier):
        with self.lock:
            row = deepcopy(self.records[identifier])
        path = Path(row["path"])
        value = json.loads(
            artifact_text(path.parent, path.name, max_bytes=64 * 1024 * 1024)
        )
        timeline = Timeline(value)
        self.viewer.register_file(path, timeline)
        return (
            "http://127.0.0.1:"
            + str(self.viewer.server_port)
            + "/?trace="
            + timeline.identity
        )


class ExperimentServer(Server):
    def __init__(self, address, experiment):
        super().__init__(address, None)
        self.RequestHandlerClass = ExperimentHandler
        self.experiment = experiment


class ExperimentHandler(Handler):
    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "Local origin required."})
        if self.path == "/api/experiment":
            return self.reply(
                200, dict(token=self.server.token, **self.server.experiment.state())
            )
        assets = {
            "/": ("experiment.html", "text/html"),
            "/experiment.js": ("experiment.js", "text/javascript"),
            "/experiment.css": ("experiment.css", "text/css"),
        }
        if self.path not in assets:
            return self.reply(404, {"error": "Not found."})
        name, mime = assets[self.path]
        self.reply(200, (Path(__file__).parent / "static" / name).read_bytes(), mime)

    def do_POST(self):
        if not self.local() or not secrets.compare_digest(
            self.headers.get("X-Study-Token", ""), self.server.token
        ):
            return self.reply(403, {"error": "Local study token required."})
        if self.headers.get("Content-Type") != "application/json":
            return self.reply(415, {"error": "JSON required."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 200000 or self.headers.get("Transfer-Encoding"):
                raise ValueError("Invalid request size.")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Expected object.")
            if self.path == "/api/experiment/run" and set(value) == {
                "caseId",
                "repetitions",
            }:
                result = dict(
                    jobId=self.server.experiment.start(
                        value["caseId"], value["repetitions"]
                    )
                )
            elif self.path == "/api/experiment/inspect" and set(value) == {"id"}:
                result = dict(url=self.server.experiment.inspect(value["id"]))
            else:
                return self.reply(404, {"error": "Unknown operation or fields."})
            self.reply(200, result)
        except (ValueError, TypeError, KeyError):
            self.reply(
                400,
                {
                    "error": "Could not complete this study request. Check the selection or active run."
                },
            )
        except Exception:
            self.reply(
                500,
                {"error": "Study operation failed; existing evidence was retained."},
            )
