# MR-E as a template: one harness, three instances

MR-E (Round-trip / Invertibility) as a *reusable test template*: (1) the template, (2) what it
checks, (3) three fillings, (4) the template as a class. Implemented in
[`families.py`](families.py) (`RoundTripMR` + three subclasses); reuses `canon` and `agent_exec`
from [`executors.py`](executors.py). The agent-level `check()` needs `OPENAI_API_KEY`.

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
| **slack** | *"Invite Dora to Slack. Dora's email is dora@example.com."* | *"Remove the user Dora from Slack."* |
| **banking** | *"Update my street address to 'Maple Avenue 5'."* | *"Update my street address to 'Apple Street 1'."* |

(Dora is not already a Slack user; `Apple Street 1` is the original address in `s₀` — the
modify-restore flavor needs it written into `P_undo`, since the second exec shares no conversation.
Calendar is excluded — `create_calendar_event` also sends an invite email and cancel only *marks*
the event, so it has no inverse.)

---

## 4. The template as an abstract class

Fixed harness = concrete `check`; holes = abstract members a subclass fills. This is the real
[`families.py`](families.py), lightly trimmed.

```python
class RoundTripMR(ABC):
    SUITE:  str        # drive: "workspace"
    P_DO:   str        # drive: "Create a file named 'scratch.txt' with the content 'hello'."
    P_UNDO: str        # drive: "Delete the file named 'scratch.txt'."

    def check(self) -> Verdict:                          # agent-level (needs OPENAI_API_KEY)
        s  = E.suite(self.SUITE)
        s0 = E.fresh_env(s)
        o1 = agent_exec(s, self.P_DO,   s0.model_copy(deep=True), "do")
        o2 = agent_exec(s, self.P_UNDO, o1.s_post,                "undo")
        return CONFORM if canon(o2.s_post, DROP) == canon(s0, DROP) else VIOLATION
```

Concrete instance (drive) — fills the holes:

```python
class DriveRoundTrip(RoundTripMR):
    SUITE  = "workspace"
    P_DO   = "Create a file named 'scratch.txt' with the content 'hello'."
    P_UNDO = "Delete the file named 'scratch.txt'."
```
