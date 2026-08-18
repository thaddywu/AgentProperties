"""120 episodes: {T1,T2,T7} x {gpt-5.6, gpt-5.5} x 20 trials. One JSONL line per episode."""
import json, sys, threading
from concurrent.futures import ThreadPoolExecutor
import checker, run as R

MODELS = ["gpt-5.6", "gpt-5.5"]
TASKS = ["T1", "T2", "T7"]
N = 20
lock = threading.Lock()
out = open("results.jsonl", "a")


def one(job):
    model, task, seed = job
    rec = {"model": model, "task": task, "seed": seed}
    try:
        p = R.episode_llm(task, seed=seed, model=model, backend="openai",
                          outdir=f"runs/{model.replace('.','')}")
        v = checker.check(p)
        rec.update(outcome=v["outcome"], violation=v["violation"], done=v["task_complete"],
                   over_refusal=v["over_refusal"], trace=p,
                   sig={k: v["signals"][k] for k in ("status_checked_t", "checker_403_t", "checker_reauth_t")})
    except Exception as e:
        rec.update(error=repr(e)[:300])
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush()
        print(rec.get("outcome", "ERR"), model, task, seed, flush=True)
    return rec


jobs = [(m, t, s) for m in MODELS for t in TASKS for s in range(N)]
with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(one, jobs))
print("DONE", len(jobs))
