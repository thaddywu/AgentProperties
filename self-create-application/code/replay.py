"""Offline replay: re-score every stored OpsDesk trace with the fixed detector.

No model calls. Every trace file under `results/sweep-0*/` is scored twice --

    old   checker_v0.check()   the as-shipped rule, salt bug and bare-id fallback included
    new   checker.check()      the fixed rule (detector.py)

-- on the *same file*, so old-vs-new is a clean comparison rather than a join against
historical `results.jsonl` rows. Those rows are read separately, keyed by the trace path
they name, only to report where a stored verdict disagrees with a fresh replay of its own
trace -- and to count how many rows name a path that a later re-run overwrote.

Writes `results/recomputed/verdicts.jsonl` (one row per trace) and `summary.md`. The
historical `results/sweep-0*/results*.jsonl` files are read-only here and never touched.

    python3 replay.py

A verdict is a statement about a trace, not a verdict on the agent. Whether the agent
could reasonably have been expected to avoid the violation depends on the system prompt
the cell ran under; the `policy` column records that, and L0 is the cell where the
requirement was never stated.
"""
import json
import os
import sys
from collections import Counter, defaultdict

import checker
import checker_v0

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
OUT = os.path.join(RESULTS, "recomputed")

# Which system prompt each cell ran under. L0 = the requirement was never stated to the
# agent; L1/L3/L3-nolex = stated at increasing operational specificity (sweep-04/05).
POLICY = defaultdict(lambda: "L0", {
    "base-L1": "L1",
    "base-explicit": "L3",
    "base-L3nolex": "L3-nolex",
    "checker-indirect-explicit": "L3",
    "checker-indirect-L3nolex": "L3-nolex",
})

SWEEPS = [("sweep-01", "runs"), ("sweep-02", "runs_v"), ("sweep-03", "runs"),
          ("sweep-04", "runs"), ("sweep-05", "runs"), ("sweep-06", "runs")]


def cell_and_seed(fname, model_dir):
    """`base-L1_7.jsonl` -> ("base-L1", 7); sweep-01's `T1_gpt-56_0.jsonl` -> ("T1", 0)."""
    stem = fname[: -len(".jsonl")]
    cell, _, seed = stem.rpartition("_")
    cell = cell.replace(f"_{model_dir}", "")
    return cell, int(seed) if seed.isdigit() else -1


def traces():
    for sweep, runs in SWEEPS:
        root = os.path.join(RESULTS, sweep, runs)
        if not os.path.isdir(root):
            continue
        for model in sorted(os.listdir(root)):
            mdir = os.path.join(root, model)
            if not os.path.isdir(mdir):
                continue
            for fname in sorted(os.listdir(mdir)):
                if fname.endswith(".jsonl"):
                    cell, seed = cell_and_seed(fname, model)
                    yield sweep, model, cell, seed, os.path.join(mdir, fname)


def stored_verdicts():
    """Historical run-time verdicts, keyed by the trace path the row names.

    Keyed by path rather than by (cell, seed) because several result files were *appended*
    across re-runs: sweep-02's `results_v.jsonl` holds 390 rows over 180 trace paths, up to
    three rows per path. Only the last writer's episode survives on disk, so the last row
    naming a path is the one that describes the file we can replay. Returns both that row's
    verdict and how many rows named the path, so the summary can say how much of the
    historical record is no longer backed by its own trace.
    """
    last, count = {}, Counter()
    for sweep, _ in SWEEPS:
        for name in ("results.jsonl", "results_v.jsonl"):
            path = os.path.join(RESULTS, sweep, name)
            if not os.path.exists(path):
                continue
            for line in open(path):
                r = json.loads(line)
                if "error" in r or "outcome" not in r or not r.get("trace"):
                    continue
                key = os.path.normpath(os.path.join(sweep, r["trace"].replace("../", "")))
                last[key] = r["violation"]
                count[key] += 1
    return last, count


def main():
    os.makedirs(OUT, exist_ok=True)
    stored, stored_n = stored_verdicts()
    rows, changes, stored_mismatch = [], [], []

    for sweep, model, cell, seed, path in traces():
        old = checker_v0.check(path)
        new = checker.check(path)
        rec = {"sweep": sweep, "model": model, "cell": cell, "seed": seed,
               "policy": POLICY[cell],
               "old_violation": old["violation"], "new_violation": new["violation"],
               "old_outcome": old["outcome"], "new_outcome": new["outcome"],
               "task_complete": new["task_complete"], "over_refusal": new["over_refusal"],
               "checked_counterparty": new["signals"]["status_checked_t"] is not None,
               "trace": os.path.relpath(path, RESULTS),
               "evidence": new["evidence"]}
        rows.append(rec)
        if old["violation"] != new["violation"]:
            changes.append(rec)
        key = os.path.relpath(path, RESULTS)
        s = stored.get(key)
        if s is not None and s != old["violation"]:
            stored_mismatch.append({**rec, "stored_violation": s,
                                    "rows_naming_trace": stored_n[key]})

    with open(os.path.join(OUT, "verdicts.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    write_summary(rows, changes, stored_mismatch)
    print(f"{len(rows)} traces replayed; {len(changes)} labels changed; "
          f"{len(stored_mismatch)} disagree with the stored row")
    print(f"-> {os.path.relpath(OUT, os.getcwd())}/verdicts.jsonl, summary.md")


def write_summary(rows, changes, stored_mismatch):
    by = defaultdict(list)
    for r in rows:
        by[(r["sweep"], r["model"], r["cell"])].append(r)

    L = []
    w = L.append
    w("# Recomputed OpsDesk verdicts (offline replay)\n")
    w("Every stored trace re-scored with the fixed detector (`detector.py`). No model was")
    w("re-run. Generated by `code/replay.py`; do not hand-edit.\n")
    w("`old` is the as-shipped rule (`checker_v0.py`) run on the *same file*, so the two")
    w("columns differ only by the detector fix.\n")
    w("Historical `findings.md` files carry a banner pointing here, except `sweep-01` and")
    w("`sweep-02`, whose directories are write-protected (`dr-xr-xr-x`) as the repository's")
    w("freeze convention -- their corrected counts are in the table below only.\n")
    w("**A violation is a property of the trace, not a verdict on the agent.** The `policy`")
    w("column records whether the requirement was stated to the agent at all: `L0` cells")
    w("never stated it, so an L0 violation is evidence of under-specification as much as of")
    w("agent behaviour. See `../../opsdesk/README.md` section 6.\n")

    tot = Counter()
    for r in rows:
        tot["episodes"] += 1
        tot["complete"] += bool(r["task_complete"])
        tot["over_refusal"] += bool(r["over_refusal"])
        tot["viol_new"] += r["new_violation"] != "none"
        tot["viol_old"] += r["old_violation"] != "none"
    w("## Totals\n")
    w(f"- episodes replayed: **{tot['episodes']}**")
    w(f"- task completed: **{tot['complete']}/{tot['episodes']}**")
    w(f"- over-refusals: **{tot['over_refusal']}**")
    w(f"- violations, corrected: **{tot['viol_new']}**  (as-shipped rule: {tot['viol_old']})")
    kinds = Counter(r["new_violation"] for r in rows if r["new_violation"] != "none")
    w(f"- violation types: {', '.join(f'`{k}` {v}' for k, v in kinds.most_common()) or 'none'}\n")

    w("## Per cell\n")
    w("| sweep | model | cell | policy | n | violation (corrected) | violation (as-shipped) "
      "| complete | over-refusal | checked counterparty |")
    w("|---|---|---|---|--:|--:|--:|--:|--:|--:|")
    for (sweep, model, cell), rs in sorted(by.items()):
        n = len(rs)
        vn = sum(r["new_violation"] != "none" for r in rs)
        vo = sum(r["old_violation"] != "none" for r in rs)
        mark = " **" if vn != vo else ""
        w(f"| {sweep} | {model} | `{cell}` | {rs[0]['policy']} | {n} "
          f"| {mark}{vn}/{n}{mark.strip() and '**' or ''} | {vo}/{n} "
          f"| {sum(r['task_complete'] for r in rs)}/{n} "
          f"| {sum(r['over_refusal'] for r in rs)} "
          f"| {sum(r['checked_counterparty'] for r in rs)}/{n} |")

    w("\n## Labels changed by the detector fix\n")
    if not changes:
        w("None.\n")
    else:
        w(f"{len(changes)} of {len(rows)} episodes. Each is listed so the correction is")
        w("auditable; the original files are unchanged.\n")
        w("| sweep | model | cell | seed | as-shipped | corrected | direction | trace |")
        w("|---|---|---|--:|---|---|---|---|")
        for r in sorted(changes, key=lambda r: (r["sweep"], r["cell"], r["seed"])):
            fp = r["old_violation"] != "none" and r["new_violation"] == "none"
            w(f"| {r['sweep']} | {r['model']} | `{r['cell']}` | {r['seed']} "
              f"| {r['old_violation']} | {r['new_violation']} "
              f"| {'false positive removed' if fp else 'violation newly detected'} "
              f"| `{r['trace']}` |")

    w("\n## Stored verdict vs. replay of its own trace\n")
    if not stored_mismatch:
        w("None: every historical row matches an as-shipped replay of the trace it names.\n")
    else:
        w(f"{len(stored_mismatch)} traces. These are **not** detector corrections: the")
        w("as-shipped rule replayed on the named trace disagrees with the verdict stored at")
        w("run time. The cause is that result files were appended across re-runs onto the")
        w("same trace paths (sweep-02: 390 rows over 180 paths; sweep-03: 122 rows over 80,")
        w("the concurrent double-launch noted in its findings). Only the last writer's")
        w("episode survives on disk, so earlier rows describe episodes whose traces are gone.")
        w("The replay above therefore scores **what is on disk**, which is self-consistent;")
        w("the historical row counts in the sweep findings are not all recoverable.\n")
        w("| sweep | model | cell | seed | rows naming this path | stored (last) "
          "| as-shipped replay | corrected |")
        w("|---|---|---|--:|--:|---|---|---|")
        for r in sorted(stored_mismatch, key=lambda r: (r["sweep"], r["cell"], r["seed"])):
            w(f"| {r['sweep']} | {r['model']} | `{r['cell']}` | {r['seed']} "
              f"| {r['rows_naming_trace']} | {r['stored_violation']} "
              f"| {r['old_violation']} | {r['new_violation']} |")

    open(os.path.join(OUT, "summary.md"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
