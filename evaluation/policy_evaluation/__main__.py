import argparse
import importlib
import json
from pathlib import Path

from .example import Application
from .importer import ReviewApplication
from .server import Server
from .study import Study


def main():
    parser = argparse.ArgumentParser(
        description="Independent local policy evaluation workbench."
    )
    parser.add_argument("--port", type=int, default=5190)
    parser.add_argument("--data", type=Path, default=Path("evaluation/output/default"))
    parser.add_argument(
        "--connection", type=Path, help="Private standard model connection JSON"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--application",
        help="Trusted installed Python module:factory implementing the runner contract",
    )
    group.add_argument(
        "--review-app",
        type=Path,
        help="Import existing pinned reference artifacts; RQ3 requires a separate runner",
    )
    group.add_argument(
        "--ported-app",
        type=Path,
        help="Accepted agentic port directory, including its pinned sandbox image",
    )
    group.add_argument('--repo', type=Path, help='Local Git repo for a new isolated Codex port')
    group.add_argument('--codex-port', type=Path, help='Existing copied Codex port output')
    group.add_argument('--back-translation', type=Path, help='Portable execution-reading directory')
    parser.add_argument('--port-output', type=Path, help='New private output directory for --repo')
    parser.add_argument('--policy', help='Original policy file; relative to source for --repo')
    parser.add_argument('--review-file', type=Path, help='Student judgment file; created if absent')
    args = parser.parse_args()
    port = None
    if args.back_translation:
        from .student_review import BundleApplication
        if not args.policy:
            parser.error('--back-translation requires --policy')
        application = BundleApplication(args.back_translation, args.policy)
    elif args.repo or args.codex_port:
        from .porting.codex import CodexPort
        from .porting.repository import RepositoryApplication

        if args.repo and (not args.port_output or not args.connection):
            parser.error('--repo requires --port-output and --connection')
        output = args.port_output if args.repo else args.codex_port
        if args.connection:
            port = CodexPort(output, json.loads(args.connection.read_text()))
        if args.repo:
            port.prepare(args.repo, args.policy)
        application = RepositoryApplication(output)
    elif args.application:
        module, factory = args.application.split(":", 1)
        application = getattr(importlib.import_module(module), factory)()
    elif args.ported_app:
        from .porting.application import PortedApplication

        application = PortedApplication(args.ported_app)
    elif args.review_app:
        application = ReviewApplication(args.review_app)
    else:
        application = Application()
    generate = None
    if args.connection:
        from policy_translation.adapters.compatible import Connection

        generate = Connection(json.loads(args.connection.read_text()))
    if args.back_translation:
        from .student_review import StudentStudy
        directory = args.back_translation.resolve()
        # Each reading/source has separate internal history. review.json is the
        # student-facing file and is checked before any judgments are resumed.
        study = StudentStudy(directory / '.review-state' / application.revision[:16], application,
                             args.review_file or directory.parent / 'review.json')
    else:
        if args.review_file:
            parser.error('--review-file requires --back-translation')
        study = Study(args.data, application)
    # A new reading gets its own version and never inherits old judgments.
    reference = application.reference()
    study.add_review(reference, reference.get("executionUsage", []))
    jobs = None
    if port:
        from .porting.repository import PortJobs
        jobs = PortJobs(port, study)
    server = Server(("127.0.0.1", args.port), study, generate, port_jobs=jobs)
    print(f"Evaluation UI: http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
