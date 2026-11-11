# Original tools with a policy hook

Original submit_job, revise_job, approve_job, dispatch_job, finish_job,
cancel_job, kill_job, record_completion, read_job, view and read_private calls
retain their original Store operations. Original ROLE_TOOLS checks also remain.

Tools.call annotates its original fn(event_id) callback with @policy.
The caller-name adapter reads role from the original Tools instance;
the annotation reads it at invocation and binds the actual tool name/arguments.
The event mapper interprets approve_job(false) as reject_job without changing the
business interface. A denial never invokes the callback.

Inside each tool branch, policy.put records the returned IDs, version, resource
specification, approval, run and allocation/counter deltas. Provenance writes are explicit at each recording site. Shared helpers handle
receipt and terminal-release assignments; there is no record_result dispatcher. Read results are not used as full-state projections. Creation puts ResourceType and the returned ResourceState. Before commit, the
SDK checks new resources against InitialState("job", "QUEUED"). Existing policy state
moves only after the result confirms the selected FSM target.

The original Store may refuse an otherwise permitted request. A refusal publishes
no EDB change. If an effect already committed but result mapping or an invariant
fails, runtime stops the scope; the backend effect is not rolled back. No arbitrary
agent fact-writing tool is exposed.

The original Bus.send body also carries guard_completion_reports(ApplicationError).
message_adapter.py binds the host-supplied sender, message type and copied body.job_id
to a send_message request. It checks permission before any original trace/inbox
side effect. A private result envelope preserves the original returned event ID;
rejection raises the original ApplicationError. Sending a report adds no EDB facts
and does not mark a job completed. Other message kinds are not checked by this hook.
