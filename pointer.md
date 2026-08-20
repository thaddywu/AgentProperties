# Pointers: 3 examples per benchmark

## 1. NVIDIA Open-SWE-Traces
Source (parquet, 20/23 shards per split): `datasets/Open-SWE-Traces/data/qwen35_openhands_trajectories/train-00000-of-00023.parquet` (2500 rows)
Extracted (row 0/1/2 of that shard, decoded to JSON):

| # | extracted | source row | instance_id | resolved |
|---|---|---|---|---|
| 1 | [examples/open-swe-traces/example_0.json](examples/open-swe-traces/example_0.json) | shard train-00000-of-00023, row 0 | creachadair__jrpc2-81 | 0 |
| 2 | [examples/open-swe-traces/example_1.json](examples/open-swe-traces/example_1.json) | shard train-00000-of-00023, row 1 | fxamacker__cbor-636 | -1 |
| 3 | [examples/open-swe-traces/example_2.json](examples/open-swe-traces/example_2.json) | shard train-00000-of-00023, row 2 | istio__istio-36706 | -1 |

Companion files (not per-example; scaffold-wide tool schemas):
- [datasets/Open-SWE-Traces/openhands_tools.json](datasets/Open-SWE-Traces/openhands_tools.json)
- [datasets/Open-SWE-Traces/sweagent_tools.json](datasets/Open-SWE-Traces/sweagent_tools.json)
- field docs: [datasets/Open-SWE-Traces/README.md](datasets/Open-SWE-Traces/README.md)

## 2. Patronus AI TRAIL
No extraction needed (plain JSON). Each example = trace file + annotation file, matched by trace_id filename.

| # | trace | annotations |
|---|---|---|
| 1 | [examples/trail/gaia_0035f455b3ff2295167a844f04d85d34.trace.json](examples/trail/gaia_0035f455b3ff2295167a844f04d85d34.trace.json) | [.annotations.json](examples/trail/gaia_0035f455b3ff2295167a844f04d85d34.annotations.json) |
| 2 | [examples/trail/gaia_0140b3f657eddf76ca82f72c49ac8e58.trace.json](examples/trail/gaia_0140b3f657eddf76ca82f72c49ac8e58.trace.json) | [.annotations.json](examples/trail/gaia_0140b3f657eddf76ca82f72c49ac8e58.annotations.json) |
| 3 | [examples/trail/swebench_0e6f7928953ab5a568bae640ce915cc3.trace.json](examples/trail/swebench_0e6f7928953ab5a568bae640ce915cc3.trace.json) | [.annotations.json](examples/trail/swebench_0e6f7928953ab5a568bae640ce915cc3.annotations.json) |

Sources (copied verbatim):
- traces: [datasets/TRAIL/data/GAIA/](datasets/TRAIL/data/GAIA/) (files 1-2, 1st and 2nd alphabetically), [datasets/TRAIL/data/SWE Bench/](datasets/TRAIL/data/SWE%20Bench/) (file 3, 1st alphabetically)
- annotations: [datasets/TRAIL/processed_annotations_gaia/](datasets/TRAIL/processed_annotations_gaia/), [datasets/TRAIL/processed_annotations_swe_bench/](datasets/TRAIL/processed_annotations_swe_bench/)

## 3. ToolBench (execution traces)
Each example = answer/trace file + query file + tool API schema (all copied verbatim into one dir).

| # | dir | query_id | source answer file |
|---|---|---|---|
| 1 | [examples/toolbench/10001/](examples/toolbench/10001/) | 10001 | datasets/ToolBench/data/answer/G1_answer/10001_ChatGPT_DFS_woFilter_w2.json |
| 2 | [examples/toolbench/10002/](examples/toolbench/10002/) | 10002 | datasets/ToolBench/data/answer/G1_answer/10002_ChatGPT_DFS_woFilter_w2.json |
| 3 | [examples/toolbench/10003/](examples/toolbench/10003/) | 10003 | datasets/ToolBench/data/answer/G1_answer/10003_ChatGPT_DFS_woFilter_w2.json |

Per-dir contents and their sources:
- `answer_<qid>.json` — from `datasets/ToolBench/data/answer/G1_answer/`
- `query_<qid>.json` — the entry with matching `query_id`, extracted from [datasets/ToolBench/data/instruction/G1_query.json](datasets/ToolBench/data/instruction/G1_query.json) (88,995 entries)
- `toolschema_newapi.json` — from [datasets/ToolBench/data/toolenv/tools/Media/newapi.json](datasets/ToolBench/data/toolenv/tools/Media/newapi.json)
- (not copied) canned API responses: [datasets/ToolBench/data/toolenv/response_examples/](datasets/ToolBench/data/toolenv/response_examples/)
