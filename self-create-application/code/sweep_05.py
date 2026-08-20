"""sweep-05: does stating the implicit rule fix it?

The base system prompt names three rules explicitly - JIT access, four-eyes review, and "access
credentials are personal and are not to be shared" - and leaves the fourth to inference: do not
hand customer rows to a principal without live access. sweep-03's traces show models discharging
the explicit credential rule while breaking the implicit data rule in the same message.

  base           the shipped prompt
  base-explicit  one sentence added in parallel with the credential sentence, naming no principal
                 and saying nothing about expiry (agent_llm.SYSTEM_EXPLICIT)

`base` is re-run here as this batch's within-batch control, because sweep-03 showed a single cell
at n=20 carries roughly +/-20 points of run-to-run noise. Run through the local reverse proxy
(OPENAI_BASE_URL=http://127.0.0.1:18080/v1), which serves resolved model ids: `gpt-5.6-sol`. Writes to ../results/sweep-05/ only; the
sweep-01/sweep-02 files and frozen/ are untouched.
"""
import json, os, threading
from concurrent.futures import ThreadPoolExecutor
import checker, variants

CELLS = os.environ.get("CELLS", "base-L1").split(",")
N = int(os.environ.get("N", "20"))
MODEL = os.environ.get("MODEL", "gpt-5.6-sol")
OUT = "../results/sweep-05"
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
