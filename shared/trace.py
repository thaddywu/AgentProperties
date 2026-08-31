"""Clock + append-only trace log, shared by every application.

Every application in `applications/` is a world with a logical clock and a JSONL trace.
A record is always::

    {"t": int, "caller": str, "tool": str, "args": {...}, "ok": bool, ...extra}

and every deterministic checker in this repository reads exactly that shape. Keeping the
record format in one place is what makes the checkers comparable across applications: a
verdict is always a statement about a trace, never about a model's reasoning.
"""
import json
import random
import string


class Clock:
    """A logical clock. Seconds are the unit everywhere; `jump` is the harness's gap."""

    def __init__(self):
        self.t = 0

    def tick(self, s=1):
        self.t += s
        return self.t


class TraceMixin:
    """Clock, salt, and trace log. Mixed into each application's world.

    `salt` exists so that a checker can recognise application data verbatim in free text
    (OpsDesk row markers, filesystem digests) without the ids being guessable from the
    prompt alone. Applications that do not need it simply ignore it.
    """

    def _init_trace(self, seed=None):
        rng = random.Random(seed)
        self.salt = "".join(rng.choice(string.hexdigits.lower()) for _ in range(4))
        self.t = 0
        self.log = []

    def tick(self, s=1):
        self.t += s
        return self.t

    def jump(self, seconds):
        """Advance the clock by a gap the episode narrates (a queue, a lunch break)."""
        self.tick(seconds)
        self._rec("system", "clock.jump", {"seconds": seconds}, True)

    def _rec(self, caller, tool, args, ok, **extra):
        r = {"t": self.t, "caller": caller, "tool": tool, "args": args, "ok": ok}
        r.update(extra)
        self.log.append(r)
        return r

    def inject(self, to, kind, body):
        """Harness-side: put a message in an inbox without any principal sending it."""
        self.inbox[to].append({"from": "system", "body": body, "t": self.t})
        self._rec("system", "inject", {"to": to, "kind": kind, "body": body}, True)

    def dump(self, path):
        with open(path, "w") as f:
            for r in self.log:
                f.write(json.dumps(r) + "\n")
        return path


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]
