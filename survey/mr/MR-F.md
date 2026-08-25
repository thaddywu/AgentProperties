# MR-F as a template: one harness, three instances

MR-F (Idempotence) as a *reusable test template*: (1) the template, (2) what it checks, (3) three
fillings, (4) the template as a class. Implemented in [`families.py`](families.py)
(`IdempotenceMR` + three subclasses); reuses `canon` and `agent_exec` from
[`executors.py`](executors.py). The agent-level `check()` needs `OPENAI_API_KEY`.

---

## 1. The template

The action runs **once** and, separately, **twice in a row** (environment threaded). The two final
states must match:

```
s₀       = fresh_env()
o1       = Exec(agent, P_do, copy(s₀))          # do it once           -> state A
twice    = Exec(agent, P_do, o1.s_post)         # do it again, from A
verdict  = ( canon(twice.s_post) == canon(o1.s_post) )   # was the 2nd application a no-op?
```

| hole | meaning | example (banking) |
|--|--|--|
| `P_do` | one self-contained action, repeated verbatim | *"Update my street address to 'Maple Avenue 5'."* |

Compare the second application to `o1.s_post` (the state right after the first do), **not** to a
separate "once" run — a second independent run of `P_do` would only differ by agent nondeterminism,
which would leak into the oracle.

## 2. What this MR checks (high level)

> **Repeating an action has no effect beyond doing it once.**

Another algebraic law of the agent's actions (`do ∘ do = do`). It catches agents that blindly
re-apply an action — double-writing, duplicating a membership, or corrupting state when asked to do
something already done. Orthogonal to MR-A (optimality) and a sibling of MR-E (`undo ∘ do = id`).

---

## 3. The three instances = three fillings

Each instance fills one hole, `P_do`. They span the three ways an action can be idempotent:

| instance | `P_do` | idempotent by |
|--|--|--|
| **banking** | *"Update my street address to 'Maple Avenue 5'."* | **the tool** — `update_user_info` is a bare field write; twice = once |
| **drive** | *"Delete the file named 'recipe-collection.docx'."* | **a no-op** — the 2nd time there's nothing to delete; state unchanged |
| **slack** | *"Add Bob to the 'private' channel, but only if he is not already a member."* | **the agent** — it must honor the guard on the 2nd run |

The slack case is the sharpest: `add_user_to_channel` is a no-dedup `append`, so a naive agent that
just re-calls it puts Bob in `private` twice → VIOLATION. The idempotence lives in the prompt's
*"only if not already"* clause, and the test is whether the agent actually checks. (A general trick:
a non-idempotent action becomes a legitimate — and harder — instance by adding such a guard.)

Preconditions: drive needs `recipe-collection.docx` to exist (it does), slack needs Bob absent from
`private` initially (he is) — otherwise both runs are no-ops and the pass is vacuous.

---

## 4. The template as an abstract class

Fixed harness = concrete `check`; the single hole = an abstract member. This is the real
[`families.py`](families.py), lightly trimmed.

```python
class IdempotenceMR(ABC):
    SUITE: str         # banking: "banking"
    P_DO:  str         # banking: "Update my street address to 'Maple Avenue 5'."

    def check(self) -> Verdict:                          # agent-level (needs OPENAI_API_KEY)
        s  = E.suite(self.SUITE)
        o1 = agent_exec(s, self.P_DO, E.fresh_env(s), "do")         # do once   -> state A
        o2 = agent_exec(s, self.P_DO, o1.s_post,      "do-again")   # do again, from A
        return CONFORM if canon(o2.s_post, DROP) == canon(o1.s_post, DROP) else VIOLATION
```

Concrete instance (slack, the guarded case) — fills the hole:

```python
class SlackGuardedAddIdempotence(IdempotenceMR):
    SUITE = "slack"
    P_DO  = "Add Bob to the 'private' channel, but only if he is not already a member."
```
