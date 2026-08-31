# Dynamic security properties in multi-agent applications

One research question:

> **When does a natural-language security policy fail to induce the runtime checks required
> to enforce a dynamic security property?**

```
Security intent  ->  Natural-language policy  ->  Operational specification
                 ->  Agent execution          ->  Runtime property
```

Each application in `applications/` is a self-contained instance of the same shape: a fact
is established by one principal, silently invalidated by another, and relied upon by an
acting agent that must re-check it. Every application varies the same two axes independently
— **what the agent is told** (policy level L0/L1/L3) and **what the workflow asks it to do**
(unsafe protocol vs protocol repair) — and reports the same table.

| | | |
|---|---|---|
| [`applications/opsdesk/`](applications/opsdesk/) | expiring access to customer data | the reference application, frozen results ([map](applications/opsdesk/CONTENTS.md)) |
| [`applications/filesystem/`](applications/filesystem/) | a reviewed release artifact that drifts | feasibility prototype |
| [`applications/cloud/`](applications/cloud/) | an approved infrastructure plan that goes stale | feasibility prototype |
| [`shared/`](shared/) | clock/trace, prompt grid, episode runner, condition sweep | [what is and is not shared](shared/README.md) |
| [`survey/`](survey/) | the earlier survey of existing agent benchmarks, and why none expressed this property | background |

The morning report comparing the three applications is
[`REPORT.md`](REPORT.md).

## Running things

Everything runs as a module from this directory. Nothing but the LLM conditions needs an API.

```
python3 -m applications.opsdesk.demo             # matched pair, deterministic
python3 -m applications.opsdesk.test_opsdesk     # 51 assertions
python3 -m applications.filesystem.demo          # matched pair, deterministic
python3 -m applications.cloud.demo               # matched pair, deterministic

OPENAI_API_KEY=dummy OPENAI_BASE_URL=http://127.0.0.1:18080/v1 \
  python3 -m applications.cloud.run --n 6        # A/B/C, real episodes
```

## Adding an application

1. `applications/<name>/DESIGN.md` — answer the seven questions before writing code:
   what fact becomes stale, who established it, who invalidates it, who must observe it,
   which runtime check is required, what happens if it is skipped, what protocol repair
   removes the need for the reasoning.
2. `world.py` — domain state and tools, on `shared.trace.TraceMixin`.
3. `protocols.py` — the unsafe protocol and the repair, differing by **one** operation.
4. `prompts/base_<protocol>.txt` + `prompts/rules/L{0,1,3,3_nolex}.txt` — the two base
   prompts must differ by exactly one hunk, and that hunk must not mention the property.
5. `check.py` — deterministic, trace-only, assigns no fault.
6. `demo.py` (scripted matched pair) and `run.py` (`shared.sweep` A/B/C grid).
