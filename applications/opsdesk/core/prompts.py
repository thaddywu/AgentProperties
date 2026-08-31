"""System prompts as a 2-axis grid: protocol base x policy level.

    build(protocol, level)  ->  the Analyst's system prompt

    protocol   "transfer"     review by sending the reviewer the rows      (the flawed one)
               "independent"  review by asking the reviewer to read them   (the repair)

    level      "L0"        the prohibition is never stated  (the shipped prompt)
               "L1"        "...disclosed only to authorized personnel"     handbook boilerplate
               "L3"        "...anyone who does not currently hold their own live access"
               "L3_nolex"  L3's semantics with the lexical anchors removed

The two axes are independent, which is the point: the **prompt mitigation** moves along the
policy axis while leaving the flawed protocol in place, and the **protocol repair** moves
along the protocol axis while leaving the ordinary L0 policy in place. See `../README.md`.

`prompts/rules/L0.txt` is empty by design -- L0 *is* the base prompt, and every rule file is
inserted at the same point, immediately after "...credentials are personal and are not to be
shared." Text lives in `prompts/` rather than in Python so a reader can diff the four
policies directly.

`test_opsdesk.py` asserts `build("transfer", L) == code/agent_llm.SYSTEM*` for every level, so
this grid and the frozen sweep harness cannot drift apart.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from shared import promptgrid  # noqa: E402

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts")

PROTOCOLS = ("transfer", "independent")
LEVELS = ("L0", "L1", "L3", "L3_nolex")


def build(protocol="transfer", level="L0"):
    return promptgrid.build(DIR, protocol, level, PROTOCOLS, LEVELS)
