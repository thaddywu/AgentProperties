# MR-E as a template: one harness, three instances

MR-E (Round-trip / Invertibility) as a *reusable test template*: (1) the template, (2) what it
checks, (3) three fillings, (4) the template as a class. Proposed family — not yet in
[`level_a.py`](level_a.py); reuses `canon` from [`instances.py`](instances.py) and the `MR`
dataclass in [`schema.py`](schema.py).

---

## 1. The template

The action and its undo run as **two consecutive executions**, the environment threaded from the
first into the second:

```
s₀       = fresh_env()
o1       = Exec(agent, P_do,   copy(s₀))        # exec 1: do
o2       = Exec(agent, P_undo, o1.s_post)       # exec 2: undo, from where exec 1 ended
verdict  = ( canon(o2.s_post) == canon(s₀) )    # undo returned the env to the start
```

| hole | meaning | example (drive) |
|--|--|--|
| `P_do` | a write action, one self-contained request | *"Create a file named 'scratch.txt' with content 'hello'."* |
| `P_undo` | its inverse, also self-contained (names its own target) | *"Delete the file named 'scratch.txt'."* |

---

## 2. What this MR checks (high level)

> **Doing an action then undoing it returns the environment to its start state.**

An algebraic property of the agent's *actions* (`undo ∘ do = identity`). It
catches agents that leave residue — undo the wrong entity, half-undo, or trip a side effect the undo
can't reverse. Orthogonal to MR-A: that asks *"did it choose well?"*, this asks *"can it cleanly
reverse itself?"*

---

## 3. The three instances = three fillings

| instance | `P_do` | `P_undo` |
|--|--|--|
| **drive** | *"Create a file named 'scratch.txt' with the content 'hello'."* | *"Delete the file named 'scratch.txt'."* |
| **slack** | *"Invite Charlie to Slack. Charlie's email is charlie@example.com."* | *"Remove the user Charlie from Slack."* |
| **banking** | *"Set my account IBAN to 'XX00 1111 2222 3333'."* | *"Set my account IBAN to '⟨original IBAN from s₀⟩'."* |

---

## 4. The template as an abstract class

Fixed harness = concrete method; holes = abstract members. Comments show the `drive` instance.
(Sketch, not literal harness code.)

```python
from abc import ABC

class RoundTripMR(ABC):
    """Do an action, then undo it, as two consecutive agent executions (environment
    threaded, conversation not); the env must return to its start. One subclass = one instance."""

    SUITE:  str        # drive: "workspace"
    P_DO:   str        # drive: "Create a file named 'scratch.txt' with content 'hello'."
    P_UNDO: str        # drive: "Delete the file named 'scratch.txt'."

    def check(self) -> bool:
        s0 = fresh_env(self.SUITE)
        o1 = run_agent(self.P_DO,   copy(s0))            # exec 1: do
        o2 = run_agent(self.P_UNDO, o1.s_post)           # exec 2: undo, threaded from o1
        return canon(o2.s_post) == canon(s0)             # returned to start? (mod id/timestamp)
```
