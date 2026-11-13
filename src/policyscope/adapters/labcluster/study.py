"""App-specific, isolated paired pilot; the post-mortem consumes only its files."""

import argparse
import json
from pathlib import Path
import shutil

from policyscope.adapters.sandbox import Sandbox
from policyscope.core.artifacts import files, save
from policyscope.core.policy import fingerprint
from policyscope.workbench.student_review import BundleApplication

SCENARIOS = {"aging", "quota", "literal", "stale", "encoded"}


def read_cases(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "cases"}
        or value["version"] != 1
    ):
        raise ValueError("Expected version-1 cases.")
    if not isinstance(value["cases"], list) or not 1 <= len(value["cases"]) <= 20:
        raise ValueError("Use 1–20 cases.")
    ids = set()
    for case in value["cases"]:
        if not isinstance(case, dict) or set(case) != {
            "id",
            "scenario",
            "task",
            "expected",
            "policies",
        }:
            raise ValueError("Invalid case fields.")
        if (
            any(
                not isinstance(case[k], str) or not 1 <= len(case[k]) <= 4000
                for k in ("id", "task", "expected")
            )
            or case["id"] in ids
            or not case["id"].replace("-", "").isalnum()
        ):
            raise ValueError("Invalid case identity or description.")
        ids.add(case["id"])
        if (
            case["scenario"] not in SCENARIOS
            or not isinstance(case["policies"], list)
            or not set(case["policies"]) <= {"P1", "P2", "P3", "P4", "P5", "P6"}
        ):
            raise ValueError("Choose a registered scenario and policy IDs.")
    return value["cases"]


class StudyRunner:
    def __init__(self, port, translated, output, *, image="policy-portin:batch-v1"):
        self.port, self.translated, self.output = map(
            lambda p: Path(p).resolve(), (port, translated, output)
        )
        self.original = self.port / "original"
        if any(
            self.output == source
            or self.output.is_relative_to(source)
            or source.is_relative_to(self.output)
            for source in (self.original, self.translated)
        ):
            raise ValueError("Keep study output outside both application directories.")
        self.source = json.loads((self.port / "source.json").read_text())
        self.reference = BundleApplication(
            self.translated / "back-translation", self.original / self.source["policy"]
        )
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.snapshots = {
            "baseline": files(self.original),
            "protected": files(self.translated),
        }
        if self.snapshots["baseline"] != self.source["files"]:
            raise ValueError("Original snapshot changed.")
        harness = self.output / "_harness"
        harness.mkdir(exist_ok=False)
        worker = harness / "study_worker.py"
        shutil.copy2(Path(__file__).with_name("study_worker.py"), worker)
        framework = harness / "framework/policyscope"
        framework.mkdir(parents=True)
        package = Path(__file__).resolve().parents[2]
        shutil.copy2(package / "__init__.py", framework / "__init__.py")
        for name in ("core", "enforcement"):
            shutil.copytree(
                package / name,
                framework / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        self.framework_hash = fingerprint(files(framework))
        self.worker_hash = fingerprint(worker.read_text())
        self.sandboxes = {
            mode: Sandbox(
                path, path, image=image, timeout=240, worker=worker, framework=framework
            )
            for mode, path in [
                ("baseline", self.original),
                ("protected", self.translated),
            ]
        }
        save(
            self.output / "provenance.json",
            dict(
                originalCommit=self.source["revision"],
                applicationFiles=self.snapshots,
                frameworkHash=self.framework_hash,
                workerHash=self.worker_hash,
                images={m: s.image for m, s in self.sandboxes.items()},
            ),
        )

    def run(self, case, *, repetitions=5, modes=("baseline", "protected")):
        read_cases(dict(version=1, cases=[case]))
        if type(repetitions) is not int or not 1 <= repetitions <= 5:
            raise ValueError("Use 1–5 repetitions.")
        if (self.output / case["id"]).exists():
            raise ValueError(
                "Case evidence already exists; choose a new output directory."
            )
        results = {}
        if not modes or any(mode not in ("baseline", "protected") for mode in modes):
            raise ValueError("Unknown study mode.")
        for mode, source in [
            ("baseline", self.original),
            ("protected", self.translated),
        ]:
            if mode not in modes:
                continue
            if files(source) != self.snapshots[mode]:
                raise ValueError("Application changed after study setup.")
            runs = []
            for repetition in range(1, repetitions + 1):
                result = self.sandboxes[mode].run(
                    dict(
                        case=case, mode=mode, repetitions=1, repetitionStart=repetition
                    )
                )
                if "runs" not in result:
                    save(
                        self.output
                        / (
                            case["id"]
                            + "-"
                            + mode
                            + "-failure-"
                            + str(repetition)
                            + ".json"
                        ),
                        result,
                    )
                    raise ValueError(
                        "Sandbox returned no execution records; inspect private failure evidence."
                    )
                runs.extend(result["runs"])
            directory = self.output / case["id"] / mode
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            for run in runs:
                run.update(
                    sourceRevision=self.source["revision"],
                    image=self.sandboxes[mode].image,
                    caseHash=fingerprint(case),
                    initialStateHash=fingerprint(run["initialState"]),
                    applicationHash=fingerprint(self.snapshots[mode]),
                    frameworkHash=self.framework_hash,
                    workerHash=self.worker_hash,
                )
                path = directory / ("run-" + str(run["repetition"]) + ".json")
                save(path, run)
            results[mode] = runs
        for original, protected in zip(
            results.get("baseline", []), results.get("protected", [])
        ):
            if (
                original["initialStateHash"] != protected["initialStateHash"]
                or original["caseHash"] != protected["caseHash"]
            ):
                raise ValueError("Paired runs do not have matching setup and cases.")
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Run frozen LabCluster cases on original and translated apps."
    )
    parser.add_argument("--port-dir", required=True, type=Path)
    parser.add_argument("--translated-app", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image", default="policy-portin:batch-v1")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--mode", choices=["both", "baseline", "protected"], default="both"
    )
    parser.add_argument("--case", help="Run one registered case ID from the case file")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Open the paired-execution UI and separate read-only analysis UI",
    )
    parser.add_argument(
        "--results", type=Path, help="Existing exported comparison directory"
    )
    parser.add_argument("--http-port", type=int, default=5192)
    parser.add_argument("--analysis-port", type=int, default=5191)
    parser.add_argument(
        "--connection",
        type=Path,
        help="Optional private model connection for analysis questions only",
    )
    args = parser.parse_args()
    cases = read_cases(json.loads(args.cases.read_text()))
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
        if not cases:
            parser.error("Unknown case ID.")
    if args.serve:
        return serve(args, cases)
    runner = StudyRunner(
        args.port_dir, args.translated_app, args.output, image=args.image
    )
    save(args.output / "frozen-cases.json", dict(version=1, cases=cases))
    for case in cases:
        results = runner.run(
            case,
            repetitions=args.repetitions,
            modes=("baseline", "protected") if args.mode == "both" else (args.mode,),
        )
        print(
            json.dumps(
                dict(
                    case=case["id"],
                    runs=sum(len(r) for r in results.values()),
                    errors=sum(
                        r["errorType"] is not None
                        for group in results.values()
                        for r in group
                    ),
                )
            ),
            flush=True,
        )


def serve(args, cases):
    import threading
    from policyscope.workbench.analysis import AnalysisServer
    from policyscope.workbench.experiment import Experiment, ExperimentServer
    from .study_export import export_run

    generate = None
    if args.connection:
        from policyscope.adapters.compatible import Connection

        generate = Connection(json.loads(args.connection.read_text()))
    viewer = AnalysisServer(
        ("127.0.0.1", args.analysis_port),
        generate=generate,
        query_directory=args.output / "queries",
    )

    def execute(case, repetitions, destination):
        runner = StudyRunner(
            args.port_dir,
            args.translated_app,
            destination / "execution",
            image=args.image,
        )
        results = runner.run(case, repetitions=repetitions)
        rows = []
        for mode, runs in results.items():
            for run in runs:
                directory = destination / "exports" / case["id"] / mode
                assessment = export_run(run, runner.original, directory)
                rows.append(
                    dict(
                        caseId=case["id"],
                        mode=mode,
                        repetition=run["repetition"],
                        taskCompleted=assessment["taskCompleted"],
                        violations=assessment["violations"],
                        timeline=str(
                            (
                                directory
                                / ("run-" + str(run["repetition"]) + ".timeline.json")
                            ).relative_to(destination)
                        ),
                    )
                )
        save(destination / "comparison.json", dict(runs=rows))
        return rows

    experiment = Experiment(cases, execute, args.output / "jobs", viewer)
    if args.results:
        rows = json.loads((args.results / "comparison.json").read_text())["runs"]
        rows = [row for row in rows if row["caseId"] in experiment.cases]
        experiment.register(rows, args.results)
        if experiment.records:
            experiment.inspect(next(iter(experiment.records)))
    server = ExperimentServer(("127.0.0.1", args.http_port), experiment)
    thread = threading.Thread(target=viewer.serve_forever, daemon=True)
    thread.start()
    print(f"Study UI: http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Analysis UI: http://127.0.0.1:{viewer.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        viewer.shutdown()
        viewer.server_close()
        thread.join()


if __name__ == "__main__":
    main()
