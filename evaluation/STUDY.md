# Student evaluation protocol

This is an executable pilot protocol, not yet a finalized study design. Students
supply policy intent and application knowledge, create scenarios, and judge results.
They do not write Datalog, adapters or runtime facts. Researchers own integration
validation and independent assessment of the enforcement boundary.

The student UI combines the RQ1/RQ2 judgments in one review. RQ3 test-file execution
is a separate command-line workflow, with evidence retained in the backend/export.
The review's literal sentence navigation is pinned
separately from model requirements. Sentence-level ratings and category counts
are exported under `sentenceReview`, without transferring older requirement-level
judgments or claiming that passage-level mappings have become sentence-precise.
Other categories can overlap with the three predefined categories and retain the
student's custom name. Task-completion judgments are separate from runner success.

## RQ1 — Policy coverage and expressiveness

1. Preserve the student's original document and its version. Distill independently
   reviewable requirements with exact source links; retain unmapped text.
2. Students check whether the decomposition preserves their intent, noting missing,
   duplicated or compound requirements. Resolve decomposition issues before using
   atomic requirements as the publication's denominator. The pilot records notes;
   an interactive split/merge editor is not implemented.
3. Students assign one or more categories using business descriptions: who may act
   (permission), where information may go (information flow), or allowed stages and
   transitions (lifecycle). Outside/uncertain are separate choices. The categories
   overlap; their percentages need not sum to 100%.
4. Separately inspect the proposed behavior/application obligations and judge full,
   partial, no, or uncertain coverage. This is a human coverage assessment, not a
   proof that an adapter supplies the required facts.
5. Researchers independently determine which requirements are supported by rules,
   installed mechanisms and tested application instrumentation. Publish missing
   observations, unsupported semantics and ambiguity separately from model errors.

Record the number of original documents, adjudicated atomic requirements, categorized
requirements, each category, outside/uncertain, and independently verified support.
Use all adjudicated requirements as the coverage denominator; retain unclassified
requirements rather than silently excluding them. Report application-level results
as well as pooled counts so a verbose application does not dominate the result.

For policies outside the three categories, the proposed experiment is a separate
predicate/schema-and-rule synthesis task: record new predicates, their meanings,
source producers, rules and independent behavioral checks. The current translator
uses an existing trusted vocabulary and **does not implement new predicate or adapter
synthesis**. An outside-category label is neither an automatic rejection nor a claim
that this extension experiment has passed. Capability, information flow and lifecycle
are categories, not optionality labels.

## RQ2 — Translation fidelity

1. Freeze the first generated candidate and its attempts. Show the unchanged source
   beside business-language readings of the actual rules. Shared rules may link to
   multiple requirements; one requirement may need multiple behaviors.
2. Students rate each requirement: fully correct, partially correct, needs improvement,
   or unsure. Partial/improvement ratings require reasons: missing content, excessive
   restriction, excessive permission, changed meaning or an application assumption.
3. Expand conditions/evidence only when needed. A record's meaning (for example,
   which outcome is considered success) comes from the trusted contract. If that
   contract lacks the meaning, ask for clarification; do not infer it from names.
4. Preserve the initial rating. Changes create a new review/version, and subsequent
   judgments remain separate. Never count a manually corrected/reference program
   as an unassisted model success.
5. Researchers inspect adapter assumptions and independently test meaningful positive,
   negative and boundary cases. A second language-model paraphrase can reproduce the
   same error; NL agreement is not semantic equivalence.

Report the rating distribution, unsure and unrated counts, omitted-source count,
structural failures, repair attempts and application-level results. All input
requirements remain in the denominator, including omissions and non-rule obligations.
Report first-attempt and repaired results separately. Record model/configuration and
usage for each generation. A requirements-only draft has no rule roundtrip. Human
coverage/rating does not authorize policy installation.

## RQ3 — Violations, useful completion and overhead

1. Students create scenarios: task, supported initial setup, expected acceptable and
   violating outcomes, seed, and development/held-out assignment. Include normal tasks,
   policy challenges and boundaries; expected outcomes must not be copied from the
   generated gate's decisions. Freeze scenarios before final testing.
2. The runner resets the application for each mode. Preserve existing application
   guards in both. Baseline disables only the added policy gate; protected enables it.
   Keep application revision, initial state, model/settings and experimental task fixed.
3. Record attempted operations, gate decisions, actual invocation/results, authoritative
   state evidence, completion and measured times. Retain failure/unknown execution
   states. The harness writes trajectories; students do not reconstruct them from chat.
4. Students judge whether a violation actually occurred and whether the attempted
   operation should have been allowed. A blocked attempt is not an executed violation.
   Independent fixture/oracle suggestions stay distinct from human judgments.
5. Repeat live agent runs with paired configurations and seeds. Alternate run order.
   Treat mismatched setup/configuration as non-comparable. Fixed-trace decision replay
   is a separate experiment; protection may change later live agent actions.

Per mode, report actual violating executions and tasks with a violation; protected
runs additionally report correctly blocked attempts and false blocks. State the unit
and denominator explicitly (events versus trials). Report useful task completion
separately: refusing everything is not successful enforcement. Retain unjudged events,
unknown outcomes, failed runs and non-comparable pairs in the dataset.

The pilot exports raw run duration and example operation-path duration. These include
engine startup and application execution; they are **not** pure inference overhead.
A model connector must report actual model tokens, request count and configuration;
no tokens are fabricated for the scripted example. Publication-quality overhead
requires fixed measurement boundaries, warm-up policy, repeated runs and separate
end-to-end versus gate-only measurements.

The default document example is deterministic and runs the installed developer
reference. Its task completion means a document was actually read. Its independent
fixture oracle uses stored ownership/state, not Datalog. It demonstrates the workflow,
not general agent performance. The legacy LabCluster `--review-app` imports review
artifacts only. The new [agentic port profile](porting/README.md) generates and
validates a candidate, then `--ported-app` runs its actual installed mapper/rules
against original deterministic LabCluster scenarios. Its six source sections are
coarse review units, not atomic requirements; RQ1 denominators must state that.
Successful scenario assertions are integration evidence, not useful-task completion
or human violation labels. A seed does not randomize this deterministic runner.
Free-form student-authored action trajectories and live-model RQ3 runners remain
integration work.

## What remains to freeze before the study

Choose participating applications and sampling rules; the model/configurations and
per-application run budget; minimum normal/challenge scenarios; policy review and
adjudication procedure; independent completion/violation criteria; and final statistical
aggregation. The tool preserves the evidence needed for these choices but does not
silently choose a sample size or claim statistical significance.

Distributed local-facts versus full-facts consistency belongs to separate automated
conformance/equivalence checks. Students should not be asked to reconstruct fact
placement from a back-translation.
