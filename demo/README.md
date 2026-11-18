# Harness translation demo

Copied from the existing LabCluster original/ported applications and the previously
generated harness. Paths now default to the application directories beside these
scripts. The scenario uses the app's explicit deterministic offline backend.

```text
demo/
  orig_app/                 Original application and synthetic fixtures
  ported_app/               Existing port, policy_port/, back-translation/, review.json
  run.py                    Original harness: --side original
  translated_harness.py     Generated entry point: original or ported
  test_cases.json            One concrete scenario and expected outcome
  step_by_step.sh            Commands and UI checkpoints
```

Read [step_by_step.sh](step_by_step.sh) for the full course flow, from Appendix A
installation through sections 3.1–3.7 and the final report. Short comments mark
UI actions and file checks. Running the shell file only prints the walkthrough. It reserves `demo/workflow/` for fresh outputs and leaves the copied
snapshots intact; those workflow outputs are not prepopulated.

The review UI automatically saves to `ported_app/review.json` on **Save**;
**Export** downloads another copy. The included [review.json](ported_app/review.json)
contains three previously saved example ratings out of 44 sentences. Open the
matching bundle from the repository root with:

```bash
policyweave view-translation --back-translation demo/ported_app/back-translation \
  --policy demo/orig_app/policies.md
```

For a remote server, forward the review port (5190) and Inspector port (5191)
to local ports and open their `http://localhost:PORT` addresses in your browser.
The local ports may differ from the server ports. Export downloads to the browser's
machine after saving the current edits. Analysis runs on the server and reports
progress while the model processes the recorded evidence.

Both harnesses load case IDs from the adjacent [test_cases.json](test_cases.json).
The demo contains one scenario with one sample per side; the full assignment
requires ten scenarios and ten samples each.

Both scripts contain the same task-completion check for `T1_priority_queue`.
The generated entry point adds APP_DIR selection, trajectory export and cumulative
task-completion reporting. `orig_app` is a copied source tree for inspection and
execution, rather than a separate Git checkout for rerunning `policyweave port`.

With PolicyWeave installed, commands from this directory are:

```bash
python run.py --case T1_priority_queue --side original --output_dir runs --sample 1
python translated_harness.py --case T1_priority_queue --side ported --output_dir runs --sample 1
```

The ported command also needs the native engine described in `../docs/setup.md`.
Results go under `runs/T1_priority_queue/<side>/sample-1/`. The generated entry
point prints cumulative completion counts for both sides and exports the ported
trajectory as JSON and JSONL. Existing sample directories are retained; use a
fresh output directory for a new batch.

To translate the original harness again, provide both app directories explicitly
and choose a new output file:

```bash
policyweave translate-harness \
  --input run.py --output retranslated_harness.py \
  --original-app orig_app --ported-app ported_app \
  --connection "$CONNECTION_FILE"
```

Both harnesses use the same command-line interface (CLI); the translated harness
adds support for `--side ported`. Pass application directories to
`policyweave translate-harness` when generating a new entry point.
This directory was assembled by copying existing artifacts; no application run
was repeated while preparing it. Run outputs, credentials and development logs
are excluded.
