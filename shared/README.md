# `shared/` — what the applications have in common

Small on purpose. Something belongs here only when at least two applications would
otherwise keep the same code twice, and moving it does not make either application harder
to read on its own.

| module | what it is | used by |
|---|---|---|
| `trace.py` | logical clock, the JSONL trace record shape, inboxes, `dump`/`load` | filesystem, cloud |
| `promptgrid.py` | system prompts as *protocol base × policy level*, read from text files | opsdesk, filesystem, cloud |
| `agentloop.py` | one `/v1/responses` tool-calling episode over a caller-supplied dispatch | filesystem, cloud |
| `sweep.py` | the A/B/C condition grid and the one results table every application prints | filesystem, cloud |

## What is deliberately *not* here

**Checkers.** Each application's checker is short, deterministic, and expresses that
application's property. Generalising them would produce a configuration language, not a
simplification. What they *do* share is the record format in `trace.py`, which is what makes
their verdicts comparable.

**Worlds.** The whole point of each application is its own domain semantics. Only the clock
and trace are common, and those are the `TraceMixin`.

**OpsDesk's runner.** `applications/opsdesk/agent.py` is the frozen ancestor of
`agentloop.py` and keeps its own copy. Every result in `applications/opsdesk/results/` was
produced by it; rewriting it in terms of the shared module would silently re-parent a frozen
result for no benefit. `applications/opsdesk/core/prompts.py` *is* retrofitted onto
`promptgrid.py`, because the OpsDesk test suite asserts its output byte-identical to the
frozen sweep harness — so that overlap is verified rather than assumed.
