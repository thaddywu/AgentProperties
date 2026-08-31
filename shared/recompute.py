"""Re-score a directory of frozen traces with the current checker.

Verdicts are recomputed rather than trusted from `results.jsonl` whenever a checker's
signals change after a sweep ran. The traces are the record; the table is derived.

    python3 -m shared.recompute applications/cloud applications/cloud/traces/attempt1
"""
import glob
import importlib
import os
import sys


def main(app, *dirs):
    check = importlib.import_module(f"{app.strip('/').replace('/', '.')}.check")
    for d in dirs:
        rows = []
        for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            if os.path.basename(f) == "results.jsonl":
                continue
            v = check.check(f)
            key = os.path.basename(f).split("_")[0]
            rows.append((key, v))
        print(f"\n{d}")
        print(f"{'':3} {'n':>3} {'violation':>10} {'complete':>9} {'checked':>8}")
        for k in sorted({r[0] for r in rows}):
            rs = [v for kk, v in rows if kk == k]
            n = len(rs)
            print(f"{k:3} {n:3} "
                  f"{sum(v['violation'] != 'none' for v in rs):>7}/{n} "
                  f"{sum(v['task_complete'] for v in rs):>6}/{n} "
                  f"{sum(v['signals']['observed_current_t'] is not None for v in rs):>5}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
