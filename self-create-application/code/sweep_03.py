"""sweep-03: is the summary condition fair? Same prefix, same expiry, same property.

Three new cells against the frozen `base`:
  base-clock    every tool return carries `t` (the Analyst gets a watch)
  base-neutral  the recap asserts no principal's credential state
  base-fixed    both

`base` is re-run here as this batch's control. Writes to ../results/sweep-03/ only; the
sweep-01/sweep-02 files and frozen/ are untouched.
"""
import json, os, threading
from concurrent.futures import ThreadPoolExecutor
import checker, variants

CELLS = ["base", "base-clock", "base-neutral", "base-fixed"]
N = int(os.environ.get("N", "20"))
MODEL = os.environ.get("MODEL", "gpt-5.6-sol")
OUT = "../results/sweep-03"
os.makedirs(OUT, exist_ok=True)

JOBS = [(MODEL, v, s) for v in CELLS for s in range(N)]
lock = threading.Lock()
out = open(f"{OUT}/results.jsonl", "a")
DONE = set()
try:
    for l in open(f"{OUT}/results.jsonl"):
        r = json.loads(l)
        if "error" not in r:
            DONE.add((r["model"], r["variant"], r["seed"]))
except FileNotFoundError:
    pass
JOBS = [j for j in JOBS if j not in DONE]


def one(j):
    model, name, seed = j
    rec = {"model": model, "variant": name, "seed": seed}
    try:
        p = variants.episode(name, seed=seed, model=model, backend="openai",
                             outdir=f"{OUT}/runs")
        v = checker.check(p)
        rec.update(outcome=v["outcome"], violation=v["violation"], done=v["task_complete"],
                   over_refusal=v["over_refusal"], trace=p, evidence=v["evidence"],
                   sig=v["signals"])
    except Exception as e:
        rec.update(error=repr(e)[:200])
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush()
        print(rec.get("outcome", "ERR"), model, name, seed, flush=True)


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(one, JOBS))
    print("DONE", len(JOBS))
