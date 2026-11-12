# Pre-restructure module archives

These branches freeze the complete pre-restructure tree, including pending Python work and shared dependencies. Each branch has its own ARCHIVE.md identifying its module. They are reference snapshots, not development branches.

| Branch | Module entry points |
| --- | --- |
| archive/policy-adder | translation/python/policy_translation/pipeline.py; evaluation/policy_evaluation/porting/ |
| archive/back-translation | translation/python/policy_translation/execution.py; porting/codex.py |
| archive/policy-viewer | evaluation/policy_evaluation/; grokbot/apps/web/src/features/policy-review/ |
| archive/enforcement | runtime/python/; runtime/src/; application ports |
| archive/post-mortem | query/python/; apps/nova/src/analysis.ts; runtime/src/souffle.ts |

The tag archive/pre-restructure-2026-11-12 identifies the shared snapshot. Earlier branch tips are retained under archive/branches-2026-11-12/ tags.

Existing public experiment artifacts remain under docs/evaluation in this snapshot. experiment-summary.json contains only selected aggregate metrics from ignored local experiment reports. Private prompts, source copies, trajectories, credentials, raw logs and private output directories are not published. Local originals and a Git bundle are retained outside tracked content.

Before restructuring, all 84 offline Python tests passed against native Souffle 2.5, including enforcement, query, translation, review and port-controller tests. These tests do not establish universal policy fidelity or arbitrary-application support.
