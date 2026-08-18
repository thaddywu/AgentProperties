"""Robustness suite: 6 T1-variants. gpt-5.6 x 20 (primary), gpt-5.5 x 10 (directional)."""
import json, threading
from concurrent.futures import ThreadPoolExecutor
import checker, variants

JOBS = ([("gpt-5.6", v, s) for v in variants.V for s in range(20)] +
        [("gpt-5.5", v, s) for v in variants.V for s in range(10)])
lock = threading.Lock(); out = open("results_v.jsonl", "a")
DONE = set()
try:
    for l in open("results_v.jsonl"):
        r = json.loads(l)
        if "error" not in r:
            DONE.add((r["model"], r["variant"], r["seed"]))
except FileNotFoundError:
    pass


def one(j):
    model, name, seed = j
    rec = {"model": model, "variant": name, "seed": seed}
    try:
        p = variants.episode(name, seed=seed, model=model, backend="openai")
        v = checker.check(p)
        rec.update(outcome=v["outcome"], violation=v["violation"], done=v["task_complete"],
                   over_refusal=v["over_refusal"], trace=p, evidence=v["evidence"],
                   sig=v["signals"])
    except Exception as e:
        rec.update(error=repr(e)[:200])
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush()
        print(rec.get("outcome", "ERR"), model, name, seed, flush=True)


with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(one, JOBS))
print("DONE", len(JOBS))
