"""Trace-level re-analysis of a sweep. Per-task, and timing-aware."""
import json, sys, collections

TTL = 1800


def load(path="results.jsonl"):
    return [json.loads(l) for l in open(path)]


def trace(r):
    return [json.loads(l) for l in open(r["trace"])]


def phase2(ev):
    return next(e["t"] for e in ev if e["tool"] == "inject" and e["args"]["kind"] == "client_followup")


def facts(r):
    """Per-episode trace facts the summary table can't show."""
    ev = trace(r); p2 = phase2(ev)
    late = [e for e in ev if e["t"] >= p2]
    f = {"checked_checker": None, "checked_self": None, "first_violation": None,
         "reads": 0, "msgs_to_checker": 0, "steps": len(late)}
    for e in late:
        if e["tool"] == "access.status" and f["checked_" + ("checker" if e["args"]["principal"] == "checker" else "self")] is None:
            f["checked_" + ("checker" if e["args"]["principal"] == "checker" else "self")] = e["t"]
        if e["tool"] == "data.read" and e["caller"] == "analyst":
            f["reads"] += 1
        if e["tool"] == "msg.send" and e["caller"] == "analyst" and e["args"]["to"] == "checker":
            f["msgs_to_checker"] += 1
    if r["violation"] != "none":
        f["first_violation"] = min(v["t"] for v in json.loads(json.dumps(r.get("evidence", []))) or [{"t": 0}]) \
            if r.get("evidence") else None
    return f


def report(rows, models, tasks):
    print("### counterparty check vs violation, PER TASK (pooling T1+T2 was misleading:")
    print("###  T2 has zero violations by construction, so pooling dilutes the T1 signal)\n")
    for m in models:
        for t in tasks:
            rs = [r for r in rows if r["model"] == m and r["task"] == t]
            if not rs: continue
            fs = [(r, facts(r)) for r in rs]
            chk = [(r, f) for r, f in fs if f["checked_checker"] is not None]
            noc = [(r, f) for r, f in fs if f["checked_checker"] is None]
            def v(g): return sum(r["violation"] != "none" for r, _ in g)
            print(f"  {m:8} {t}:  checked {v(chk)}/{len(chk)} violated   "
                  f"| not checked {v(noc)}/{len(noc)} violated")
            # did any check happen only AFTER the transfer?
            after = [r["seed"] for r, f in fs if r["violation"] != "none"
                     and f["checked_checker"] is not None
                     and f["checked_checker"] > (r["evidence"][0]["t"] if r.get("evidence") else 1e9)]
            if after:
                print(f"           (checked only AFTER sending, seeds {after})")
    print("\n### work done in phase 2 (median), by outcome class")
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        by = collections.defaultdict(list)
        for r in rs:
            by["violated" if r["violation"] != "none" else "safe"].append(facts(r))
        for k, fl in sorted(by.items()):
            med = lambda key: sorted(f[key] for f in fl)[len(fl) // 2]
            print(f"  {m:8} {k:9} n={len(fl):3}  steps {med('steps'):>2}  reads {med('reads')}  msgs-to-checker {med('msgs_to_checker')}")


if __name__ == "__main__":
    rows = load(sys.argv[1] if len(sys.argv) > 1 else "results.jsonl")
    report(rows, ["gpt-5.6", "gpt-5.5"], ["T1", "T2", "T7"])
