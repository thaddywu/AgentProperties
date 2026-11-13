import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from policyscope.core.artifacts import save
from policyscope.workbench.analysis import AnalysisServer
from policyscope.workbench.experiment import Experiment, ExperimentServer


class ExperimentTests(unittest.TestCase):
    def test_registered_runner_is_only_invoked_for_authorized_bounded_requests(self):
        example = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "examples/trajectories/team-review.json"
            ).read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            viewer = AnalysisServer(("127.0.0.1", 0), example)
            started, release = threading.Event(), threading.Event()
            calls = []

            def execute(case, repetitions, destination):
                calls.append((case["id"], repetitions))
                started.set()
                release.wait(5)
                save(destination / "trace.json", example)
                return [
                    dict(
                        caseId=case["id"],
                        mode="baseline",
                        repetition=1,
                        taskCompleted=True,
                        violations=[],
                        timeline="trace.json",
                    )
                ]

            experiment = Experiment(
                [
                    dict(
                        id="fixture", task="Synthetic task", expected="Synthetic result"
                    )
                ],
                execute,
                directory,
                viewer,
            )
            server = ExperimentServer(("127.0.0.1", 0), experiment)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def post(route, value, token=None):
                return urlopen(
                    Request(
                        base + "/api/experiment/" + route,
                        data=json.dumps(value).encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-Study-Token": token or server.token,
                        },
                    ),
                    timeout=5,
                )

            try:
                for value, status in [
                    (dict(caseId="fixture", repetitions=6), 400),
                    (dict(caseId="unknown", repetitions=1), 400),
                    (
                        dict(caseId="fixture", repetitions=1, command="host command"),
                        404,
                    ),
                ]:
                    with self.assertRaises(HTTPError) as error:
                        post("run", value)
                    self.assertEqual(error.exception.code, status)
                with self.assertRaises(HTTPError) as error:
                    post("run", dict(caseId="fixture", repetitions=1), "wrong")
                self.assertEqual(error.exception.code, 403)
                self.assertEqual(calls, [])
                job = json.load(post("run", dict(caseId="fixture", repetitions=1)))[
                    "jobId"
                ]
                self.assertTrue(started.wait(2))
                with self.assertRaises(HTTPError):
                    post("run", dict(caseId="fixture", repetitions=1))
                release.set()
                experiment.thread.join(5)
                self.assertEqual(calls, [("fixture", 1)])
                self.assertEqual(experiment.state()["job"]["status"], "completed")
                self.assertTrue((Path(directory) / job / "job.json").is_file())
                record = experiment.state()["records"][0]
                self.assertNotIn("path", record)
                response = json.load(post("inspect", dict(id=record["id"])))
                self.assertTrue(response["url"].startswith("http://127.0.0.1:"))
                self.assertEqual(viewer.timeline.export(), example)
                with self.assertRaises(HTTPError):
                    post("inspect", dict(id="../../outside"))
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                viewer.server_close()
                thread.join()
