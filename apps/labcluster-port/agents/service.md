# Original agent and scenario code

Professor, PhD and Master use the original prompts, Tools objects and decision
loop. Scenario and Runner keep receiving Store, not Policy. Trace remains the
original SQLite-backed causal trace, including its business-state snapshots.

The composition root creates the original Store and attaches store.policy = adapt().
The Tools.call instrumentation annotates its original callback with @policy; no agent or scenario file
is modified. Host-assigned role identities remain the original demo convention,
not a login/authentication implementation.

run.py executes the original deterministic backend and scenario code with the
instrumented tool and structured-report boundaries. The original Bus.send body
is retained under a decorator; only COMPLETION_REPORT receives the new ownership
check. Other message kinds and the injected direct Store fault remain unmediated. No new model call is claimed.
