from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from policyscope.analysis.timeline import Timeline
from policyscope.workbench.analysis import AnalysisServer

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/trajectories/team-review.json"


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EXAMPLE.read_text())

    def test_directed_messages_tool_correlation_and_export_are_data_only(self):
        self.value["events"][0]["content"] = "<script>not executable</script>"
        self.value["events"][0]["data"] = {"outcome": {"toString": None}}
        with patch("subprocess.run", side_effect=AssertionError("No host commands")):
            timeline = Timeline(self.value)
            self.assertEqual(timeline.event("m1")["recipients"], ["professor"])
            self.assertIsNone(timeline.describe()["events"][0]["outcome"])
            self.assertEqual(
                timeline.event("r1")["callId"], timeline.event("c1")["callId"]
            )
        exported = timeline.export()
        self.assertEqual(exported, self.value)
        exported["events"].clear()
        self.assertEqual(len(timeline.describe()["events"]), 6)
        del self.value["events"][0]["timestamp"]
        self.assertNotIn("timestamp", Timeline(self.value).describe()["events"][0])

    def test_ambiguous_roles_order_time_and_tool_results_are_rejected(self):
        mutations = [
            lambda v: v["roles"].append(v["roles"][0]),
            lambda v: v["events"][0].update(actor="invented"),
            lambda v: v["events"][0].update(recipients=["invented"]),
            lambda v: v["events"][0].update(sequence=1),
            lambda v: v["events"][0].update(timestamp="2026-11-13T09:00:00"),
            lambda v: v["events"][4].update(callId="invented"),
            lambda v: v.update(connection={"baseUrl": "http://127.0.0.1/v1"}),
            lambda v: v.update(version=True),
        ]
        for mutate in mutations:
            value = deepcopy(self.value)
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                Timeline(value)

    @unittest.skipUnless(
        shutil.which("souffle") and shutil.which("prlimit"),
        "Native fixture generation required",
    )
    def test_existing_gate_logs_are_viewed_without_running_the_engine(self):
        from policyscope.enforcement import Policy

        with tempfile.TemporaryDirectory() as directory:
            rules = Path(directory) / "rules.dl"
            rules.write_text('Allow(Q) :- Request(Q,"professor","dispatch").\n')
            policy = Policy(rules, trace=True)
            try:
                policy.call(
                    "student", "dispatch", {}, lambda: self.fail("Blocked callback")
                )
                trace = policy.trajectory()
            finally:
                policy.runtime.close()
        with patch(
            "policyscope.core.datalog.Souffle.evaluate",
            side_effect=AssertionError("No replay"),
        ):
            timeline = Timeline(trace)
            event = timeline.describe()["events"][0]
            self.assertEqual(event["outcome"], "blocked")
            self.assertFalse(timeline.event(event["id"])["data"]["effectCalled"])
            self.assertEqual(timeline.export(), trace)

    def test_local_http_import_is_atomic_and_has_no_execution_or_model_routes(self):
        server = AnalysisServer(("127.0.0.1", 0), self.value)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(route, value, *, token=None, origin=None):
            headers = {
                "Content-Type": "application/json",
                "X-Study-Token": token or server.token,
            }
            if origin:
                headers["Origin"] = origin
            return urlopen(
                Request(
                    base + "/api/analysis/" + route,
                    data=json.dumps(value).encode(),
                    headers=headers,
                ),
                timeout=5,
            )

        try:
            catalog = json.load(urlopen(base + "/api/analysis", timeout=5))
            identity = catalog["trajectory"]["id"]
            for route in ["ask", "run", "verify", "send", "execute"]:
                with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                    post(route, {})
                self.assertEqual(error.exception.code, 404)
            for headers in [
                dict(token="wrong"),
                dict(origin="https://example.invalid"),
            ]:
                with self.assertRaises(HTTPError) as error:
                    post("import", dict(trajectory=self.value), **headers)
                self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                post("import", dict(trajectory={"path": "rules.py"}))
            self.assertEqual(error.exception.code, 400)
            self.assertEqual(
                json.load(urlopen(base + "/api/analysis"))["trajectory"]["id"], identity
            )
            self.assertEqual(
                json.load(post("event", dict(trajectoryId=identity, eventId="m1")))[
                    "result"
                ]["recipients"],
                ["professor"],
            )
            changed = dict(self.value, title="A different log")
            json.load(post("import", dict(trajectory=changed)))
            with self.assertRaises(HTTPError) as error:
                post("event", dict(trajectoryId=identity, eventId="m1"))
            self.assertEqual(error.exception.code, 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
