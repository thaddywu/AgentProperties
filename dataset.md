# Datasets
- tau-bench (2024)
    - Task domain: (1) airline agent, (2) retail agent
    - Rules:
        - datasets/tau-bench/tau_bench/envs/retail/rules.py
            - "For any change to the backend database, e.g., address update, refund, or order cancellation, the agent must confirm the transaction details with the user and ask for permission, and get explicit authorization (yes) to proceed.",
        - datasets/tau-bench/tau_bench/envs/airline/wiki.md
    - NL properties. 
- AgentDojo (Neurips 2024)
    - Task domain: (1) banking (2) slack (3) travel (4) workspace
    - What it contains:
        - Task goal: datasets/agentdojo/src/agentdojo/default_suites/v1/workspace/user_tasks.py
        - Injection goal: datasets/agentdojo/src/agentdojo/default_suites/v1/workspace/injection_tasks.py
        - Injection endpoint: datasets/agentdojo/src/agentdojo/data/suites/workspace/injection_vectors.yaml
- AgentC (ICLR 2026)
    - Built on top of tau-bench.
    - Main contribution: turn NL properties -> temporal logic formula on tool call traces. (violation rate: Qwen3-32B ~30%, Claude Opus4.5 and GPT5 ~30%)
    - Not released (https://github.com/structuredllm/agent-c)
- AgentSpec
    - Action-level security enforcement
- TRAJECT-Bench
    - TODO
---
# Why coding task hard to define temporal constraints?
- SWE-bench has no constraints on the trace but only require e.g. the bug to be fixed.
- ordering is usually heuristic but not necessary
    - [ok] read file A -> edit file A
    - [ok] read some context -> edit file A without reading A
- need to model states.
    - customer service agent usually has clear states, such as the inventory already in a database

---

# What can possibly be done?
- semantic constraints.
    - neuro-symbolic
    - 
