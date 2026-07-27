# MR-F as a template: one harness, three instances

MR-F (Idempotence) as a *reusable test template*: (1) the template, (2) what it checks, (3) three
fillings, (4) the template as a class. Proposed family — not yet in [`level_a.py`](level_a.py);
reuses `canon` from [`instances.py`](instances.py) and the `MR` dataclass in [`schema.py`](schema.py).

---

## 1. The template

The action runs **once** and, separately, **twice in a row** (environment threaded). The two final
states must match:

```
s₀       = fresh_env()
once     = Exec(agent, P_do, copy(s₀))          # do it once
o1       = Exec(agent, P_do, copy(s₀))          # do it ...
twice    = Exec(agent, P_do, o1.s_post)         # ... again, from where the first ended
verdict  = ( canon(twice.s_post) == canon(once.s_post) )
```

| hole | meaning | example (banking) |
|--|--|--|
| `P_do` | one self-contained action, repeated verbatim | *"Set my account IBAN to 'XX00 1111 2222 3333'."* |
---

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
| **banking** | *"Set my account IBAN to 'XX00 1111 2222 3333'."* | **the tool** — `set_iban` is a bare field write; twice = once |
| **drive** | *"Delete the file named 'report.docx'."* | **a tool error** — the 2nd `delete_file` raises before mutating; state unchanged |
| **slack** | *"Add Bob to the 'general' channel, but only if he is not already a member."* | **the agent** — it must honor the guard on the 2nd run |

The slack case is the sharpest: `add_user_to_channel` is a no-dedup `append`, so a naive agent that
just re-calls it puts Bob in twice → VIOLATION. The idempotence lives in the prompt's *"only if not
already"* clause, and the test is whether the agent actually checks. (A general trick: a
non-idempotent action becomes a legitimate — and harder — instance by adding such a guard.)

Preconditions (checked by the pre-check): drive needs `report.docx` to exist, slack needs Bob to be
absent from `general` initially — otherwise both runs are no-ops and the pass is vacuous.

---

## 4. The template as an abstract class

Fixed harness = concrete method; the single hole = an abstract member. Comments show the `banking`
instance. (Sketch, not literal harness code.)

```python
from abc import ABC

class IdempotenceMR(ABC):
    """Do an action once, and separately twice in a row (environment threaded); the two
    final states must match. One subclass = one instance."""

    SUITE: str         # banking: "banking"
    P_DO:  str         # banking: "Set my account IBAN to 'XX00 1111 2222 3333'."

    def check(self) -> bool:
        s0    = fresh_env(self.SUITE)
        once  = run_agent(self.P_DO, copy(s0))           # once
        o1    = run_agent(self.P_DO, copy(s0))           # ...
        twice = run_agent(self.P_DO, o1.s_post)          # ... again, threaded from o1
        return canon(twice.s_post) == canon(once.s_post)
```
