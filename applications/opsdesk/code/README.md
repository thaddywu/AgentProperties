# code — frozen implementation

    python3 run.py                                   # 7 stand-in policies x 3 tasks -> checker verdicts
    python3 checker.py <trace.jsonl>                 # one verdict, with evidence
    python3 analyze.py ../results/sweep-01/results.jsonl
    OPENAI_API_KEY=... python3 run.py --agent openai --model gpt-5.6 --task T1 --trials 1

| file | what |
|---|---|
| `desk.py` | the world: one table, bearer credentials (30-min TTL), messages, virtual clock, JSONL log. Five tools. |
| `run.py` | episode driver for T1/T2/T7, the scripted Checker, and 7 stand-in Analyst policies. |
| `checker.py` | deterministic verdict from a trace. No LLM. |
| `variants.py` | the six T1 robustness variants (wording, domain, intervening work). |
| `agent_openai.py` | Analyst on OpenAI models (`gpt-5.6` needs `/v1/responses`). |
| `agent_llm.py` | Analyst on Anthropic models — **untested**, no key in this environment. |
| `sweep.py` / `sweep_v.py` | the two batch runs. They write to `../results/*-rerun/` so the frozen record cannot be clobbered. |
| `analyze.py` | trace-level re-analysis (per-task, timing-aware). |

Two things a newcomer trips on: `gpt-5.6` rejects function tools on `/v1/chat/completions`, and
`variants.py` swaps datasets by rebinding `desk.ROWS`, so dataset changes must be serialized —
`sweep_v.py` runs orders-variants and claims-variants in separate phases for exactly that reason.
