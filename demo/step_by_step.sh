#!/usr/bin/env bash
# Prints the demo steps without executing them. Paths start at the repo root.
cat <<'WALKTHROUGH'
set -euo pipefail

# step 0. installation (Appendix A)
./install.sh
source .venv/bin/activate
export CONNECTION_FILE="$HOME/.config/policyweave/connection.yaml"
# Configure this file using examples/connection.yaml.

# Prepare a fresh private workspace from the existing demo snapshot.
RUN_DIR="$(policyweave new-run Labcluster)"
export RUN_DIR
cp -R demo/orig_app "$RUN_DIR/orig_app"
cp "$RUN_DIR/orig_app/requirements.md" "$RUN_DIR/orig_app/app.md"
cp "$RUN_DIR/orig_app/policies.md" "$RUN_DIR/orig_app/policy.md"
git -C "$RUN_DIR/orig_app" init
git -C "$RUN_DIR/orig_app" add .
git -C "$RUN_DIR/orig_app" commit -m "Prepare original demo application"
export ORIGINAL_APP_DIR="$RUN_DIR/orig_app"
export PORTED_APP_DIR="$RUN_DIR/ported_app"

# step 1. policy translation (sec 3.1)
policyweave port --input "$ORIGINAL_APP_DIR" --output "$PORTED_APP_DIR" --connection "$CONNECTION_FILE"
# Check $PORTED_APP_DIR/back-translation/ exists.
policyweave view-translation --back-translation "$PORTED_APP_DIR/back-translation" --policy "$ORIGINAL_APP_DIR/policy.md"
# Open http://127.0.0.1:5190. Review and Save.
# Check $PORTED_APP_DIR/review.json (saved automatically).

# step 2. test scenarios (sec 3.2)
# Copy the one-case smoke scenario; extend to 10 scenarios for the assignment.
cp demo/test_cases.json "$RUN_DIR/test_cases.json"
# Describe each task, initial state and expected outcome; this is the test specification.
# See demo/test_cases.json for one example. Step 3 implements executable tests.

# step 3. test harness (sec 3.3)
# Implement the scenarios and completion checks in $RUN_DIR/run.py.
cp demo/run.py "$RUN_DIR/run.py"
# Read APP_DIR and check_result in $RUN_DIR/run.py.
policyweave translate-harness --input "$RUN_DIR/run.py" --output "$RUN_DIR/translated_harness.py" \
  --original-app "$ORIGINAL_APP_DIR" --ported-app "$PORTED_APP_DIR" --connection "$CONNECTION_FILE"
# Check $RUN_DIR/translated_harness.py exists.

# step 4. original app (sec 3.4)
python "$RUN_DIR/translated_harness.py" --case T1_priority_queue --side original --output_dir "$RUN_DIR/results" --sample 1
# Check $RUN_DIR/results/T1_priority_queue/original/sample-1/result.json.

# step 5. ported app (sec 3.6)
python "$RUN_DIR/translated_harness.py" --case T1_priority_queue --side ported --output_dir "$RUN_DIR/results" --sample 1
# Check $RUN_DIR/results/T1_priority_queue/ported/sample-1/result.json and trajectory.json exist.

# step 6. Inspector (sec 3.7)
policyweave inspect --traj "$RUN_DIR/results/T1_priority_queue/ported/sample-1/trajectory.jsonl" --connection "$CONNECTION_FILE" --data "$RUN_DIR/queries"
# Open http://127.0.0.1:5191. Select a call, view Database, and ask a question in QA.

# step 7. report (secs 4-5)
# Review both result.json files and write $RUN_DIR/report.md.
WALKTHROUGH
