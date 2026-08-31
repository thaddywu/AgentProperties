"""Run a condition grid and print the one table every application reports.

Each application defines conditions of the same three kinds, so that the applications
answer the same conceptual question and their tables can be laid side by side:

    A  unsafe protocol   + implicit policy (L0)   baseline
    B  unsafe protocol   + operational policy     specification mitigation
    C  repaired protocol + implicit policy (L0)   protocol repair

The `checked` column is the mechanistic one: it counts episodes in which the agent
performed the runtime check that the dynamic property requires. B is expected to work *by
making the agent establish the fact*; C is expected to work *without the agent needing
to*.
"""
import json
import os


def run_grid(conditions, keys, n, episode, outdir, model=None, verbose=True):
    """`episode(key, cond, seed, model, outdir) -> dict` with keys
    outcome / violation / done / checked / trace.

    `n` is an episode count, or a dict keyed by condition when the conditions are not run
    at the same size (a probe may want more of the treatment than of its control).
    """
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for k in keys:
        c = conditions[k]
        nk = n[k] if isinstance(n, dict) else n
        if verbose:
            print(f"\n[{k}] {c['label']}  n={nk}", flush=True)
        for seed in range(nk):
            r = episode(k, c, seed, model, outdir)
            r["condition"], r["seed"] = k, seed
            rows.append(r)
            if verbose:
                print(f"  {k} seed={seed:<3} {r['outcome']:5} violation={r['violation']:22} "
                      f"done={int(r['done'])} checked={int(r['checked'])}", flush=True)
    with open(os.path.join(outdir, "results.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows


def table(conditions, keys, rows, title=""):
    out = [title] if title else []
    out.append(f"{'':3} {'condition':44} {'n':>3} {'violation':>10} {'complete':>9} {'checked':>8}")
    for k in keys:
        rs = [r for r in rows if r["condition"] == k]
        if not rs:
            continue
        n = len(rs)
        out.append(f"{k:3} {conditions[k]['label']:44} {n:3} "
                   f"{sum(r['violation'] != 'none' for r in rs):>7}/{n} "
                   f"{sum(r['done'] for r in rs):>6}/{n} "
                   f"{sum(r['checked'] for r in rs):>5}/{n}")
    return "\n".join(out)
