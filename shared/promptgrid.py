"""System prompts as a 2-axis grid: protocol base x policy level.

Every application in this repository varies the same two axes, and they must be varied
*independently*, because the whole research question is which axis induces the runtime
check:

    protocol axis   what the workflow asks the agent to do   (unsafe / repaired)
    policy axis     what the agent is told                   (L0 / L1 / L3)

Text lives in files under `<app>/prompts/` rather than in Python so that the four policies
can be diffed directly, and so that the only difference between two conditions is visible
as a diff hunk.

    prompts/base_<protocol>.txt   contains the literal token {RULE}
    prompts/rules/<level>.txt     inserted at that point; L0.txt is empty by design
"""
import os


def build(dirpath, protocol, level, protocols=None, levels=None):
    if protocols and protocol not in protocols:
        raise ValueError(f"protocol must be one of {protocols}, got {protocol!r}")
    if levels and level not in levels:
        raise ValueError(f"level must be one of {levels}, got {level!r}")

    def read(*parts):
        with open(os.path.join(dirpath, *parts)) as f:
            return f.read()

    return read(f"base_{protocol}.txt").replace("{RULE}", read("rules", f"{level}.txt")).rstrip("\n")
