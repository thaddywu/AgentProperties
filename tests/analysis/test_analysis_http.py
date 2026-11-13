import json
from pathlib import Path
import shutil
import threading
import tempfile
from copy import deepcopy
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from policyscope.workbench.analysis import AnalysisServer
from policyscope.analysis.timeline import Timeline


@unittest.skipUnless(
    shutil.which("souffle") and shutil.which("prlimit"),
    "Native query execution required",
)
class AnalysisHttpTests(unittest.TestCase):
    def test_analysis_model_has_only_read_only_query_authority(self):
        example = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "examples/trajectories/team-review.json"
            ).read_text()
        )
        requests = []

        def model(stage, prompt):
            payload = json.loads(prompt)
            requests.append(payload)
            if payload["question"] == "future":
                return json.dumps(
                    dict(unsupported="Finite logs do not prove future behavior.")
                )
            return json.dumps(
                dict(query="?- Recipient(E,R).", explanation="Recorded recipients")
            )

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
                    "ask",
                    dict(trajectoryId=identifier, question="Who received messages?"),
                )
            )["result"]
            self.assertEqual(result["rowCount"], 4)
            self.assertNotIn("inputs", requests[0])
            self.assertNotIn("events", requests[0])
            response = json.load(
                post("ask", dict(trajectoryId=identifier, question="future"))
            )["result"]
            self.assertEqual(response["status"], "unsupported")
            self.assertNotIn("rows", response)
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
