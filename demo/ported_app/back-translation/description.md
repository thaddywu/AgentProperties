# Added enforcement

## Role permission to view

Records: Before Trace.tool invokes view, the gate reads the host-bound caller and configured role membership. Professor, PhD and Master are the configured permitted callers.

Rules: ProfessorRole or StudentRole permits the view callback. Runner and Unbound have no Allow. Permission does not validate returned contents.
The app's existing read filtering and Professor-only eligible queue remain necessary. Direct view access has no added gate.

## Role permission to read private fixtures

Records: Before Trace.tool invokes read_private, the gate reads the host-bound caller and configured role membership. It does not read a resource or content selector.

Rules: ProfessorRole or StudentRole permits read_private; other callers have no Allow. The original tool selects all three fixtures for Professor or only the bound-role fixture for PhD and Master.
Returned data from an arbitrary callback is unchecked. Direct fixture access, message bodies and model contexts have no added private-content gate.

## Professor read of an existing job

Records: Before Trace.tool invokes read_job, the gate reads the host-bound caller, requested job ID and a fresh saved-job snapshot.

Rules: ProfessorRole and a saved job matching the requested job ID permit the read callback, regardless of owner. A missing job ID or job supplies no Professor Allow.
If neither Professor nor student read Allow holds, an explicit Deny returns only status UNAVAILABLE. Direct job reads still depend on the app's existing read check.

## Student read permission

Records: Before Trace.tool invokes read_job, the gate reads the host-bound caller, requested job ID and a fresh saved-job snapshot.

Rules: StudentRole, an existing requested job and the existing-job ownership check permit the callback. The Professor read branch is separate.
If neither read branch supplies Allow, an explicit Deny returns only status UNAVAILABLE. Arbitrary callback results are unchecked; direct reads depend on the app's existing access check.

## Student permission to submit

Records: Before Trace.tool invokes submit_job, the gate reads the host-bound caller's capability. Before the registered submission mutation, it reads that capability again inside the transaction.

Rules: StudentRole grants submit permission to PhD and Master at both gates. Other callers lack Allow. Submission ownership, requested node type and the applicable role resource limits must separately pass at mutation.
An explicit Deny overrides mutation Allow. The app's existing specification and owner validation can refuse before the mutation gate; permission does not override those results.

## Submission owner equals caller

Records: During submit_job, immediately before the registered mutation, the gate reads the actual owner argument and host-bound caller. Normal Tools.call supplies its bound role as owner.

Rules: The observed owner must equal the caller. A different or missing owner prevents submission Allow. Submit permission and the other submission checks remain separate.

## Student permission to revise

Records: Before Trace.tool invokes revise_job, the gate reads caller capability, requested job ID and saved ownership. It rereads actual invocation values and transaction state before the registered revision mutation.

Rules: StudentRole revision capability and the existing-job ownership check are required at both gates. Missing permission or a matching owned job prevents Allow.
The queued-state, requested-node-type and applicable role resource checks separately govern mutation; any Deny overrides Allow. The app's existing specification validation can still refuse.

## Saved ownership for student actions

Records: For read_job, revise_job, finish_job and cancel_job, the gate reads caller identity and the saved owner of the requested job. Interface checks use request job IDs; mutation checks use actual invocation job IDs and transaction state.

Rules: Each student branch requires a saved job with that job ID and owner equal to the caller. Missing ownership evidence prevents student Allow; it does not grant capability or satisfy other action checks.
Professor read, finish and kill branches do not require this equality. Failed student reads share UNAVAILABLE with missing jobs; other policy refusals generally also project UNAVAILABLE.

## Revision requires queued state

Records: During revise_job, immediately before the registered mutation, the gate reads the owned job's saved state from the transaction. The interface permission does not test state.

Rules: The owned job must be QUEUED for revision Allow. A present different state explicitly denies NOT_QUEUED. Missing state prevents Allow. Ownership and other revision checks remain separate.

## Requested node type must exist

Records: During submit_job or revise_job, before the registered mutation, the gate reads the actual validated proposed node type and saved nodes from the transaction.

Rules: At least one saved node must have exactly the proposed node type. No match or missing type prevents mutation Allow, even when other checks pass.
Busy nodes can satisfy this check; cores and memory are not compared here. The app's existing specification validation additionally restricts types to CPU or GPU.

## PhD resource limits

Records: submit_job and revise_job supply the actual proposed resource request at mutation. Positive approve_job reads the saved owner and request before its callback; dispatch_job reads them at mutation. Bounds are fixed rule constants.

Rules: PhD requests must meet all limits: 1–8 CPU cores, 1–32 GB memory and 1–60 minutes runtime, inclusive. Missing or invalid numeric values and excess values prevent Allow rather than deriving QUOTA_EXCEEDED.
Positive approval accepts CPU or GPU within these limits. Submission and revision also need requested-node-type; dispatch needs physical-capacity. The broad numeric condition also supports Master effects, subject to Master limits.
Rejection is exempt. Direct approval mutation has no added resource check; the app's existing approval and candidate resource checks remain necessary and may additionally refuse.

## Master resource limits

Records: submit_job and revise_job use the actual caller and proposed request at mutation. Positive approve_job and dispatch_job use the saved owner and request. Limits are fixed rule constants.

Rules: Master requests require CPU and all limits: 1–4 CPU cores, 1–8 GB memory and 1–20 minutes runtime, inclusive. Positive approval uses this exact branch; rejection is exempt.
At submission, revision and dispatch, any cores >4, memory >8, runtime >20 or non-CPU type explicitly denies QUOTA_EXCEEDED, overriding broad numeric Allow. These denies select the caller for submission/revision and saved owner for dispatch.
The broad numeric check supplies lower bounds; missing or invalid numbers prevent Allow, not zero-fill. Ownership checks remain necessary. Direct approval mutation has no added resource bound.

## Professor permission to approve

Records: Before Trace.tool invokes approve_job, the gate reads caller capability, the approve input and saved job. Before the registered approval mutation, it rereads capability and job state in the transaction.

Rules: Positive interface approval requires ProfessorRole approval capability, approve=true, the applicable role resource branch, review-queued and review-version. Missing requirements prevent Allow.
The mutation gate requires approval capability and an existing queued job, without inspecting the decision or resource request. It does not bind the method's actor argument to the gate caller.
Direct approval therefore still needs the app's existing actor, decision-type, version and acceptance-only resource checks. No added rule requires the Professor to approve.

## Professor permission to reject

Records: Before Trace.tool invokes approve_job, the gate reads caller capability, approve=false, the requested job and saved review facts. The mutation gate rereads capability and queued state, but not the decision or version.

Rules: Rejection requires ProfessorRole approval capability, an existing job, review-queued and review-version. No resource limit applies, so an over-limit request can be rejected. Missing requirements prevent Allow.
There is no separate reject capability. The common approval mutation branch delegates the decision and version handling to the app's existing approval checks, which remain necessary for direct calls.

## Review requires queued state

Records: For approve_job, the gate reads saved job state immediately before the interface callback and again inside the transaction before the registered approval mutation.

Rules: Approval and rejection both require QUEUED at each gate. For an approval-capable caller targeting an existing job, a present different state explicitly denies NOT_QUEUED. Missing state prevents Allow.

## Review names the current task version

Records: Before Trace.tool invokes approve_job, the gate compares the actual expected_version input with the saved current task version for the requested job.

Rules: Either decision must name the same queued job's current task version. Missing expected_version prevents Allow. With approval capability, queued state and both versions present, inequality explicitly denies STALE_TASK_VERSION.
The approval mutation gate does not bind the version or decision. Direct approval calls still need the app's existing version check.

## Professor permission to start

Records: Before Trace.tool invokes dispatch_job, the gate reads caller capability, requested job ID and saved job existence. Before the registered start mutation, it uses the actual invocation job ID and transaction state.

Rules: ProfessorRole dispatch capability and an existing matching job permit the interface callback. This permission alone does not require queued state, approval or free resources.
Mutation repeats dispatch capability and requires every separate dispatch effect check, with no matching Deny. The app's existing Professor actor guard remains necessary because the gate does not bind the method actor argument.
No automatic dispatch or preemption of running jobs is added.

## Start requires a queued student job

Records: During dispatch_job, immediately before the registered start mutation, the gate reads the target's saved state and owner's configured role from the transaction.

Rules: The target must be QUEUED and owned by a StudentRole member for mutation Allow. Missing state or student ownership prevents Allow.
For a dispatch-capable caller, any present non-QUEUED target state explicitly denies NOT_QUEUED, independently of approval. Starting permission is checked separately.

## Current approval before start

Records: dispatch_job reads the target and saved approval before mutation. Only after approval commits and returns ok exactly True with an approval result does the per-Store record capture approve_job, the actual caller, applied outcome and approval ID.

Rules: The target's non-null approval ID must select one Professor-issued approval for the same job ID, current task version, unchanged task details and exact resource request. That approval also needs an applied approve_job event whose actor is Professor and whose approval ID matches.
For a dispatch-capable caller and queued target, explicitly null approval ID denies APPROVAL_REQUIRED_FOR_CURRENT_VERSION. Other missing or mismatched approval evidence prevents Allow.
The app's existing approval check must additionally enforce the current policy digest. Saved issuer text alone cannot replace the required successful Professor event.

## Free node capacity before start

Records: During dispatch_job, immediately before the registered start mutation, the gate reads the saved request and current node allocation, type, CPU cores and memory from the transaction.

Rules: One saved node must have no run, exactly the requested type, at least the requested CPU cores and at least the requested GB of memory. All conditions must hold on that same node. No such node or missing required values prevents Allow.
Runtime is not a physical-capacity comparison. The witness node is not bound to the node the app selects, so the app's existing allocation logic remains necessary. This check adds no NO_FREE_MATCHING_NODE Deny.

## PhD before an unaged Master

Records: Before dispatch_job mutates, the gate reads target and contender state, approval evidence, resources, node type and waiting_dispatches. The counter starts at 0; only successful original dispatches increment other eligible same-type candidates.

Rules: Given broad target Allow, a Master target with waiting_dispatches <3 is denied PRIORITY_CONFLICT if any distinct queued same-type PhD contender passes current-approval, PhD resource limits and physical-capacity. Its free-node witness may differ from the target's.
Missing contender or counter evidence prevents this Deny, not necessarily dispatch Allow. The threshold is fixed at 3 dispatch opportunities, not elapsed time or saved aging configuration; blocked attempts do not age jobs.

## Aged Master before PhD

Records: Before dispatch_job mutates, the gate reads target and contender state, approval evidence, resource requests, node type and waiting_dispatches. Successful original dispatches age other eligible same-type candidates; failed attempts and elapsed time do not.

Rules: Given broad target Allow, a PhD target is denied PRIORITY_CONFLICT if any distinct queued same-type CPU Master contender has waiting_dispatches >=3 and passes current-approval, Master resource limits and physical-capacity.
Submission order does not affect this Deny. The contender may fit a different free node from the target. Missing required contender or counter evidence prevents this Deny, not necessarily dispatch Allow.

## PhD submission order

Records: Before dispatch_job mutates, the gate reads target and contender submission sequences, state, approval evidence, resource requests and nodes. Submission records submission_seq as the number of saved jobs plus 1.

Rules: Given broad target Allow, deny a PhD target PRIORITY_CONFLICT if any distinct queued same-type PhD contender has a strictly smaller submission sequence and passes current-approval, PhD resource limits and physical-capacity.
The contender may fit a different free node. Equal sequences do not trigger this Deny. Missing contender, sequence or approval evidence prevents this Deny, not necessarily dispatch Allow.

## Master submission order within aging tiers

Records: Before dispatch_job mutates, the gate reads Master target and contender submission sequences, waiting_dispatches, approval evidence, resource requests and nodes. Counters age only through successful original dispatches of eligible same-type candidates.

Rules: Given broad target Allow, deny PRIORITY_CONFLICT for a distinct queued same-type CPU Master contender with a smaller submission sequence when both counters are <3 or both are >=3. The contender must pass current-approval, Master resource limits and physical-capacity.
Its free-node witness may differ from the target's. Equal sequences and an aged target facing an unaged contender do not trigger this Deny. Missing required counter, sequence or contender evidence prevents this Deny, not necessarily dispatch Allow.

## Aged Master blocks an unaged Master

Records: Before dispatch_job mutates, the gate reads Master target and contender state, waiting_dispatches, approval evidence, numeric requests and free-node fields. Counters age only through successful original dispatches of eligible same-type candidates.

Rules: Given broad target Allow and target waiting_dispatches <3, deny PRIORITY_CONFLICT if a distinct queued Master contender has waiting_dispatches >=3, passes current-approval and Master numeric limits, and shares the target's type with a free node.
Node capacity fields must exist, but this branch does not compare them with contender demand or explicitly require contender CPU type. It can therefore block for a contender that cannot fit. Submission order is irrelevant.
Missing required contender, counter, approval or node evidence prevents this Deny, not necessarily dispatch Allow. The original scheduler cannot undo this Deny and may additionally refuse calls the added layer permits.

## Runner permission to record completion

Records: Before Trace.tool invokes record_completion, the gate reads caller capability, the run_id input and saved run existence. Before the registered receipt mutation, it rereads capability and the actual invocation run ID against transaction state.

Rules: SimulatorRole, whose configured member is Runner, must grant record_completion capability, and the run ID must match a saved run. Missing capability or run prevents Allow at either gate.
Historical runs and duplicate results can pass this permission. Receipt creation does not require a currently running allocation, elapsed duration or real execution evidence.

## Professor permission to finish

Records: Before Trace.tool invokes finish_job, the gate reads caller role, requested job ID and saved job existence. Before the registered finish mutation, it rereads the actual invocation and transaction state.

Rules: ProfessorRole and an existing target permit the interface callback without owner equality. Mutation requires the same role alternative plus finish-running, finish-allocation and finish-receipt. Missing requirements prevent Allow.
The gate does not bind the method actor argument to its caller; the app's existing read-access check remains necessary.

## Student permission to finish

Records: Before Trace.tool invokes finish_job, the gate reads caller capability, requested job ID and saved ownership. It rereads actual invocation values and saved transaction state before the registered finish mutation.

Rules: StudentRole finish capability and existing-job-ownership permit the interface callback. Mutation repeats both and separately requires finish-running, finish-allocation and finish-receipt. Missing requirements prevent Allow.
Interface permission does not establish running state or valid completion evidence. Student statements and model reports do not replace the required receipt.

## Finish requires running state

Records: During finish_job, immediately before the registered mutation, the gate reads saved target state, saved ownership and caller role from transaction state.

Rules: Successful finish branches require RUNNING; missing state prevents Allow. For the saved owner or ProfessorRole, QUEUED explicitly denies NOT_RUNNING.
For those callers, any present state other than QUEUED or RUNNING, including an unknown state, explicitly denies STALE_REPORT_IGNORED. Owner-based denies need no finish capability, but cannot grant it.

## Finish matches the live allocation

Records: During finish_job, immediately before the registered mutation, the gate reads the target's current task version and details, current run, saved run identity and saved node allocation and generation.

Rules: The RUNNING job's current run must belong to that job ID and match its current task version and unchanged task details. The run's node must still hold that run ID at the same generation. All matches must hold together.
Missing or mismatched allocation evidence prevents Allow. finish-receipt is separate: a receipt alone cannot release a changed allocation.

## Finish requires a witnessed completion receipt

Records: finish_job reads its actual receipt_id and saved receipts before mutation. record_completion builds a successful simulator receipt from a saved run; only after commit and ok exactly True with a nonduplicate receipt does the per-Store record capture the actual caller, applied event and receipt ID.

Rules: The requested receipt must be kind completion, source SimulatedRunner and exit_code=0, matching finish-allocation's job ID, run ID, node ID, generation and unchanged task details.
An applied record_completion event with actor Runner and that same receipt ID is also required. Missing or mismatched evidence prevents Allow; duplicate results do not create missing event evidence.
Simulator success needs no elapsed runtime or external execution proof. Saved source text or model reports are insufficient. Nested release must separately pass release-allocation and release-evidence.

## Professor permission to kill

Records: Before Trace.tool invokes kill_job, the gate reads caller capability, requested job ID, saved target and supplied reason. Before the registered stop mutation, it reads the actual invocation reason and transaction state.

Rules: ProfessorRole kill capability, an existing target and a supplied reason are required at both gates, without owner equality. Missing requirements prevent Allow. kill-cancel-reason and kill-cancel-state apply separately.
Running-job release also needs release-allocation and release-evidence. No urgency, managerial decision or semantic justification is required. The app's existing actor check remains necessary because the method actor is not bound to the gate caller.

## Student permission to cancel

Records: Before Trace.tool invokes cancel_job, the gate reads caller capability, requested job ID, saved ownership and supplied reason. The shared stop mutation reads actual invocation values and transaction state.

Rules: StudentRole cancel capability, existing-job-ownership and a supplied reason are required at interface and mutation gates. Missing requirements prevent Allow. kill-cancel-reason and kill-cancel-state apply separately.
Running-job release also needs release-allocation and release-evidence. These rules add neither student kill_job permission nor a Professor cancel_job branch.

## Supplied reason for kill or cancellation

Records: kill_job and cancel_job expose the actual reason input before the interface callback and the actual invocation reason before mutation. The app validates reason text before reaching the mutation gate.

Rules: Added permission branches require reason presence; a missing reason prevents Allow. They do not require nonempty or meaningful content. The app's existing text check requires a nonblank valid UTF-8 string of at most 1200 characters.
Reason bodies otherwise remain unchecked for justification or private content. Only the separate exact-key persistence scan may block registered credential strings when the reason is persisted.

## Kill and cancellation state check

Records: During kill_job or cancel_job, immediately before the registered mutation, the gate reads the saved target state from the transaction.

Rules: Positive permission has no state restriction. A present state differing from all of QUEUED, RUNNING, COMPLETED and TERMINATED explicitly denies UNAVAILABLE. Missing state does not trigger this Deny and can reach an original state-access error.
QUEUED permits original termination without release. RUNNING permits a stop attempt subject to confirmation and nested release. COMPLETED or TERMINATED permits original ALREADY_TERMINAL no-op success, not an added refusal.

## Release matches the exact live allocation

Records: Before nested release clears a node, the gate reads current transaction state and actual node/run IDs. unsafe_release_by_node also checks its node_id and old_run_id inputs before its interface and mutation callbacks.

Rules: The requested node must hold the requested run. That saved run must name the same node and generation, and its job must still be RUNNING with that run ID, unchanged task details and current task version equal to the run's job version.
The same allocation must pass release-evidence. If neither full release alternative holds, including missing fields or changed generation, an explicit Deny returns ALLOCATION_CHANGED before clearing the node.
No caller capability is required; even LegacyCallback or Unbound can pass these matches. Nested refusal raises ApplicationError and rolls back the original mutation; unsafe_release_by_node returns a policy refusal.

## Completion or confirmed stop before release

Records: Before release, the gate reads saved receipts and prior applied completion events. record_completion supplies committed completion evidence; kill_job appends a stop receipt only after simulated stop succeeds, immediately before nested release in the same transaction.

Rules: Some SimulatedRunner receipt must match release-allocation's job ID, run ID, node ID, generation and unchanged task details. Completion requires kind completion, exit_code=0 and an applied Runner record_completion event for that receipt ID.
Alternatively, kind stop with confirmed_stopped=true suffices, without an event, exit code or supplied receipt-ID match. Evidence is existential, not bound to finish_job's receipt_id. Missing both alternatives yields release-allocation's explicit ALLOCATION_CHANGED Deny.
Stop evidence relies on saved simulator confirmation, not external attestation; forged matching stop records can satisfy it. Original stop failure returns before receipt append or release.

## Exclude configured keys from persisted events

Records: Before Trace.add appends or persists an event, the gate counts registered key occurrences in all actual bound/default arguments except self, including actor, kind, payloads, references and visibility. Keys enter the registry after successful DeepSeekBackend construction with a nonempty API key.

Rules: Allow requires a zero count; nonzero or missing measurement explicitly denies UNAVAILABLE and raises ApplicationError before append or insert. Counting is exact and case-sensitive across string values and dictionary keys, recursively through lists and tuples; an empty registry counts zero.
Unknown, transformed or split keys, bytes and other sensitive content are not protected. Framework telemetry, direct writes and alternative transports are outside this gate. Monitoring redacts configured keys only on its model_output path, not the original event data.
Tool or model effects can precede observation persistence; refusal does not undo them. Framework tracing can observe arguments before this gate, and separate run observation can expose state.

## Exclude configured keys from provider bodies

Records: Before DeepSeekBackend.request and each original 429 retry, the gate counts registered key occurrences in the actual body. Successful backend construction registers a nonempty API key. Authentication headers are not part of the measurement.

Rules: Allow requires zero exact case-sensitive occurrences in recursive string values and dictionary keys, including lists and tuples. An empty registry or body=None counts zero. Nonzero or missing measurement explicitly denies UNAVAILABLE and raises BackendError before request construction or send.
Unknown, transformed or split keys and bytes evade scanning; other private message or model-context content is unchecked. Endpoint, headers, wire encoding and responses are outside the scan; the Authorization header still carries the key.
Framework telemetry and alternative transports are outside this gate. It adds no external-access allowlist; the app's existing endpoint validation, TLS, budgets and retry logic remain responsible for those constraints.

## Exclude configured keys from evaluator exports

Records: Before phase1.run.export creates directories or writes files, the gate counts registered key occurrences across actual data and its rendered Markdown. Successful backend construction registers a nonempty API key. Markdown rendering occurs before the gate and can itself fail.

Rules: Allow requires a combined zero count; nonzero or missing measurement explicitly denies UNAVAILABLE and raises ApplicationError before export writes. Counting is exact and case-sensitive through string values, dictionary keys, lists and tuples; an empty registry counts zero.
The scan includes scenario_id in data but excludes the output path. Unknown, transformed or split keys, bytes and other private content are not protected. Framework exports, direct writes and alternative transports remain outside this gate.
The exporter renders Markdown again rather than writing frozen scanned bytes. This gate does not make the JSON and Markdown writes atomic.
