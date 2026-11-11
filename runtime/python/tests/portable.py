"""Compare policy identity, decisions and closures against TypeScript-produced fixtures."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_runtime import compile_policy
from policy_runtime.datalog import Souffle, decode, encoded_fact
from policy_runtime.policy import decide, installed_rules

fixtures = json.loads(Path(sys.argv[1]).read_text())
for case in fixtures:
    bundle = compile_policy(case["binding"], case["source"])
    assert bundle["hash"] == case["hash"], case["name"] + ": cross-language policy identity mismatch"
    rules = installed_rules(case["binding"], case["source"])
    decision = decide(case["binding"], bundle["hash"], rules, case["inputs"], case["request"])
    assert decision["allowed"] == case["allowed"], case["name"] + ": decision mismatch"
    facts = Souffle().evaluate([encoded_fact(f) for f in case["inputs"]], rules)
    normalized = sorted(json.dumps([f["predicate"], *map(decode, f["args"])], ensure_ascii=False, separators=(",", ":")) for f in facts)
    assert normalized == sorted(case["closure"]), case["name"] + ": closure mismatch"
print("Portable policy identities, complete closures and decisions agree.")
