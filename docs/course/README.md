# CS239 Phase 2

Read the [Phase 2 instructions](phase2-instructions.pdf) for the assignment.

This repository includes the PolicyWeave source, installer and a copied
[LabCluster demo](demo/README.md). The [walkthrough](demo/step_by_step.sh)
shows the course steps; running that script only prints the commands.

## Install PolicyWeave

On Linux x86_64, with Python 3.10+ and a running Docker daemon:

    git clone https://github.com/thaddywu/CS239-Phase2.git
    cd CS239-Phase2
    ./install.sh
    source .venv/bin/activate

The installer prepares the framework, native engine and translation tools.
See [manual setup](docs/setup.md) if a prerequisite is missing.
The Python core and deterministic demo need no hosted model.
Translation and Inspector QA use your private model connection.

Copy [the connection template](examples/connection.yaml) outside this checkout,
fill the selected provider's connection, and use that same file throughout the
course. Application runtime dependencies remain application-owned.

## Course commands

    policyweave port --input "$ORIGINAL_APP_DIR" --output "$PORTED_APP_DIR" --connection "$CONNECTION_FILE"
    policyweave view-translation --back-translation "$PORTED_APP_DIR/back-translation" --policy "$ORIGINAL_APP_DIR/policy.md"
    policyweave translate-harness --input run.py --output translated_harness.py --original-app "$ORIGINAL_APP_DIR" --ported-app "$PORTED_APP_DIR" --connection "$CONNECTION_FILE"
    python translated_harness.py --side original --output_dir runs --sample 10
    python translated_harness.py --side ported --output_dir runs --sample 10
    policyweave inspect --traj runs/S01/ported/sample-1/trajectory.jsonl --connection "$CONNECTION_FILE"

See the PDF for application paths, test-case requirements and deliverables.
Review **Save** writes PORTED_APP_DIR/review.json automatically.

## Included examples

- [Demo](demo/README.md): copied original/ported apps, both harnesses, a scenario,
  a matching review bundle and sample judgments.
- [Quickstart](examples/quickstart/quickstart.py): small native enforcement example.
- [Porting and harness guide](docs/porting.md)
- [Trajectory contract](docs/trajectory.md) and [Inspector](docs/timeline.md)
- [Repository structure](docs/repository-structure.md)

The editable course source is phase2-instructions.tex, with figures in images/.
Releases are generated from the [development repository](https://github.com/thaddywu/AgentProperties);
`release.json` records the framework and course-source revisions.
The framework is Apache-2.0 licensed; see [LICENSE](LICENSE).
