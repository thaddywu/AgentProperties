"""Optional egress content filter. **Not** the safe/unsafe difference.

This is defence in depth, available to *both* protocols via `World(dlp=True)` and off by
default in both. It is deliberately orthogonal to the protocol axis so that the paired
comparison in `../demo.py` never depends on heuristic content detection:

    protocol axis      transfer-review  vs  independent-review   <- the repair
    hardening axis     dlp=False        vs  dlp=True             <- optional, either protocol

Reuses `code/detector.py` so that what the filter blocks and what the offline audit scores
are one definition of "discloses a row".

## What it cannot do

It is a content detector, so it loses to obfuscation. Measured against this implementation:

    "r40 was refunded two hundred forty-four dollars and ten cents"   delivered
    "D. Whitfield: refunded"                                          delivered
    base64 of a row                                                   delivered
    one row per message, described in prose                           delivered
    "the first customer alphabetically there got their money back"    delivered

So `dlp=True` blocks the disclosure shapes the replayed corpus actually produced -- verbatim
and lightly-redacted pastes -- and nothing subtler. It is not non-interference, and no claim
in this artifact rests on it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "code"))
import detector  # noqa: E402


def would_disclose(world, to, body):
    """Rows this body would put in `to`'s hands that `to` does not already hold."""
    candidates = [r[0] for r in world.rows if r[0] not in world.held.get(to, set())]
    return detector.disclosed_rows(body, candidates, world.salt)
