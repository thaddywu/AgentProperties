# LabCluster with an incremental policy adapter

The original student Store owns the simulated cluster's jobs, approvals, runs,
receipts, nodes and trace. Its business methods, schema validation, permission
checks and scheduler remain unchanged. Original agent prompts, decision loop,
scenario choreography and message bus remain in the pinned checkout.

Instrumentation inside core/tools.py annotates the original callback with @policy.
Policy rules check the bound request before the operation; inline policy.put calls
record confirmed result deltas in the policy EDB. Initial reviewed groups, quotas, nodes and FSM
configuration live in rules.dl. There is no per-call Store-to-EDB projection.
A decorator on original Bus.send also checks structured COMPLETION_REPORT ownership
before the original trace or inbox delivery. Other message types are unchanged.

The SDK manages keys, EDB validation and policy-state transitions after confirmed
business results. InitialState configures creation by resource type. Store and
EDB commits are not one transaction; uncertain synchronization stops the session.
The adapter starts from a fresh Store/scope and does not implement restart recovery.

Other original message types, contexts, exports and deliberately unsafe direct Store paths
are not fully mediated. Provenance records actual tool evidence references; it
is not a complete information-flow guarantee.
