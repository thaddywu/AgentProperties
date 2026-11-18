import json
from pathlib import Path
import shutil
import threading
import tempfile
import time
from copy import deepcopy
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from policyweave.workbench.analysis import AnalysisServer
from policyweave.analysis.timeline import Timeline


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"),
    "Native query execution required",
)
class AnalysisHttpTests(unittest.TestCase):
    def test_background_explanation_reconnects_and_retains_success_or_failure(self):
        example = json.loads((Path(__file__).resolve().parents[2]
                              / "examples/trajectories/team-review.json").read_text())
        started, release = threading.Event(), threading.Event()
        fail = False

        def model(stage, prompt):
            started.set()
            if not release.wait(5):
                raise TimeoutError()
            if fail:
                raise RuntimeError("synthetic-private-detail")
            return '{"status":"answered","answer":"Synthetic answer."}'

        def explain(*args, **kwargs):
            return json.loads(args[3]("call-analysis-answer", "{}"))

        with tempfile.TemporaryDirectory() as directory:
            server = AnalysisServer(("127.0.0.1", 0), example, model, directory)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            request = dict(trajectoryId=server.timeline.identity,
                           eventId=example["events"][0]["id"], templateId="decision", background=True)

            def post(value, token=None):
                return urlopen(Request(base + "/api/analysis/explain", json.dumps(value).encode(),
                    headers={"Content-Type": "application/json", "X-Study-Token": token or server.token}), timeout=2)

            def job(identifier, terminal=False):
                deadline = time.monotonic() + 5
                while True:
                    result = json.load(urlopen(base + "/api/analysis/jobs/" + identifier, timeout=2))
                    if not terminal or result["status"] != "running":
                        return result
                    if time.monotonic() > deadline:
                        self.fail("Background explanation did not finish")
                    threading.Event().wait(0.01)

            try:
                with patch("policyweave.workbench.analysis.analyze_call", side_effect=explain):
                    with post(request) as response:
                        self.assertEqual(response.status, 202)
                        identifier = json.load(response)["jobId"]
                    self.assertTrue(started.wait(2))
                    self.assertEqual(job(identifier)["phase"], "explanation")
                    self.assertEqual(json.load(post(request))["jobId"], identifier)
                    self.assertEqual(json.load(urlopen(base + "/api/analysis"))["trajectory"]["id"], request["trajectoryId"])
                    with self.assertRaises(HTTPError) as error:
                        post(dict(request, templateId="effect"))
                    self.assertEqual(error.exception.code, 409)
                    with self.assertRaises(HTTPError) as error:
                        post(request, token="wrong")
                    self.assertEqual(error.exception.code, 403)
                    release.set()
                    result = job(identifier, terminal=True)
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(result["response"]["result"]["answer"], "Synthetic answer.")
                    fail = True
                    failed = job(json.load(post(request))["jobId"], terminal=True)
                    self.assertEqual(failed["status"], "failed")
                    self.assertNotIn("synthetic-private-detail", json.dumps(failed))
                    self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)
                    fail = False
                    self.assertEqual(job(json.load(post(request))["jobId"], terminal=True)["status"], "completed")
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                thread.join()

    def test_analysis_model_has_only_read_only_query_authority(self):
        example = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "examples/trajectories/team-review.json"
            ).read_text()
        )
        requests = []

        def model(stage, prompt):
            self.fail("Fixed log templates and direct queries need no model call.")

        server = AnalysisServer(("127.0.0.1", 0), example, model)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(route, value):
            return urlopen(
                Request(
                    base + "/api/analysis/" + route,
                    data=json.dumps(value).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "X-Study-Token": server.token,
                    },
                ),
                timeout=5,
            )

        try:
            metadata = json.load(urlopen(base + "/api/analysis"))
            identifier = metadata["trajectory"]["id"]
            self.assertTrue(metadata["modelAvailable"])
            result = json.load(
                post(
                    "query",
                    dict(trajectoryId=identifier, query="?- Recipient(E,R)."),
                )
            )["result"]
            self.assertEqual(result["rowCount"], 4)
            with patch(
                "policyweave.analysis.session.QuerySession.query",
                side_effect=AssertionError("Preview executed a query."),
            ):
                plan = json.load(
                    post(
                        "translate",
                        dict(
                            trajectoryId=identifier,
                            templateId="recipient-events",
                            parameters=dict(recipient="master"),
                        ),
                    )
                )["result"]
            self.assertEqual(plan["status"], "ready")
            self.assertNotIn("rows", plan)
            answered = json.load(
                post("answer", dict(trajectoryId=identifier, planId=plan["planId"]))
            )["result"]
            self.assertEqual(answered["rowCount"], 2)
            self.assertEqual(answered["answer"]["source"], "deterministic-template")
            self.assertEqual(len(requests), 0)
            with self.assertRaises(HTTPError):
                post("answer", dict(trajectoryId=identifier, planId="unknown"))
            for operation in ("ask", "translate"):
                with self.assertRaises(HTTPError):
                    post(operation, dict(trajectoryId=identifier, question="future"))
            for query in [
                "Allow(Q) :- Request(Q,A,E).",
                '.include "outside"',
                "?- Secret(X).",
            ]:
                with self.assertRaises(HTTPError) as error:
                    post("query", dict(trajectoryId=identifier, query=query))
                self.assertEqual(error.exception.code, 400)
            self.assertEqual(json.load(urlopen(base + "/api/analysis/export")), example)
            with tempfile.TemporaryDirectory() as directory:
                first = Path(directory) / "first.json"
                second = Path(directory) / "second.json"
                first.write_text(json.dumps(example))
                other = deepcopy(example)
                other["title"] = "Second snapshot"
                second.write_text(json.dumps(other))
                one, two = Timeline(example), Timeline(other)
                server.register_file(first, one)
                server.register_file(second, two)
                with self.assertRaises(HTTPError):
                    post(
                        "answer", dict(trajectoryId=two.identity, planId=plan["planId"])
                    )
                selected = json.load(
                    urlopen(base + "/api/analysis?trace=" + one.identity)
                )
                self.assertEqual(selected["trajectory"]["title"], example["title"])
                self.assertEqual(
                    json.load(
                        post(
                            "query",
                            dict(trajectoryId=one.identity, query="?- Observed(E)."),
                        )
                    )["result"]["rowCount"],
                    6,
                )
                self.assertEqual(
                    json.load(
                        urlopen(base + "/api/analysis/export?trace=" + two.identity)
                    ),
                    other,
                )
                first.write_text(json.dumps(other))
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/api/analysis?trace=" + one.identity)
                self.assertEqual(error.exception.code, 409)
            for operation in ("send", "execute", "run"):
                with self.assertRaises(HTTPError) as error:
                    post(operation, {})
                self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
