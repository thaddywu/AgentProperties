# LabCluster Tasks 3–5 development pilot

Completed 2026-11-13. Five frozen cases ran on the actual original and translated
LabCluster tools/store in network-disabled containers, five repetitions per mode
(50 executions). The application used an explicit offline deterministic agent
fixture, with zero application-model requests. The analysis experiment used a real
compatible LLM independently of the application. These are development scenarios
and reproducibility checks, not independent live-agent trials or human judgments.

## Original versus translated execution

Each cell reports completed legitimate tasks / runs, then runs with at least one
observed policy finding. Completion is separately defined by designated job IDs
reaching COMPLETED; an injected invalid submission is not a legitimate goal.

| Case | Original completion | Original runs with findings | Translated completion | Translated runs with findings |
| --- | ---: | --- | ---: | --- |
| Aging boundary | 5/5 | 0/5 | 5/5 | 0/5 |
| Over-quota admission | 5/5 | 5/5: P1 | 5/5 | 0/5 |
| Literal private-data disclosure | 5/5 | 5/5: P2 | 5/5 | 0/5 |
| Stale allocation release | 0/5 | 5/5: P4, P6 | 5/5 | 0/5 |
| Encoded private-data disclosure | 5/5 | 5/5: P2 | 5/5 | 5/5: P2 |
| Total | 20/25 | 20/25 | 25/25 | 5/25 |

The stale callback releases a node already reassigned to another run, preventing
the new job from completing. The translated gate prevents that release. The
encoded case deliberately retains a counterexample: reversible base64 content
reaches the other student despite the translated app's literal-content check.
The translated app was frozen rather than repaired to eliminate that result.

The oracle examines actual state transitions and message receipts. It does not
take generated gate decisions as policy truth. An independently authored Python
fixture assessment and a researcher-authored historical Datalog profile agree on
completion and findings for all 50 exported logs. This is implementation agreement
under finite checks, not independent human validation or full original-policy
coverage. Repeated P4 findings can reflect one persistently broken allocation;
finding rows are not counted as independent incidents.

## Questions, queries and answers

Six questions were interpreted once in each case/mode context: 60 real model
requests, with no structural repair requests. Three questions correspond to
provided examples (completion, observed violations and gate refusals), two extend
beyond examples (disclosure details and the first P4 observation joined to its
operation), and one asks for an unsupported universal future-safety proof.

All 50 supported translations returned the required semantic fields and correct
rows against the Python assessment/raw observations. All ten unsupported requests
returned unsupported. Reusing each supported query on the other four repetitions
produced 200 further correct answers: 250 supported native answers in total.
Evaluation recovers fields from predicate argument positions, independently of
variable names/order, and requires the P4 operation join. Missing required fields
or semantic relations fail even for an empty result set. This is not a held-out
accuracy estimate. The saved model usage totals 313,754 reported tokens.

Examples from the recorded answers:

```prolog
?- TaskStatus(C,S,E).
?- Violation(E,P,R).
?- GateBlocked(E,A,T).
?- Disclosure(E,Sender,Recipient,Owner,Transformation).
?- FirstObservedViolation(E,"P4",R), Operation(E,A,T).
```

In the original stale-allocation run, the last query returns event `E0079`,
`running_job_lost_allocation`, actor `LegacyCallback` and tool
`unsafe_release_by_node`. This identifies the earliest observed failure and its
associated operation, without claiming an intervention-based causal proof. In the
translated encoded-disclosure run, the disclosure query returns event `E0102`,
sender `PhD`, recipient `Master`, owner `PhD` and transformation `base64`.

The model receives only the question, predicate schema/meanings, analysis Datalog,
scope, examples and entity IDs. Inspection of all 60 saved prompts confirmed that
input shape. It receives no app Python, raw fact rows, message bodies or expected
answers. The backend validates the bounded read-only query, evaluates it locally
and displays exact rows with semantic field labels and recorded-event links.
The model does not summarize result rows or invent an answer after execution.

## UI and evidence

The execution UI runs a selected case in both modes and opens each result in a
separate pinned observer tab. The analysis UI reads the timeline and optional
analysis contract; it cannot converse with the recorded agents or run app tools.
Headless checks exercised import, directed messages, event links, direct queries,
NL query rendering, unsupported questions and separate original/translated tabs.
A further browser check used the actual sandbox runner and analysis model for the
quota case. The generic offline suite passed 109 tests.

The [walkthrough](../study/labcluster-pilot.md) contains commands and artifact
formats. The [aggregate JSON](labcluster-pilot.json) records measured counts and
hashes. Raw fixture JSONL, normalized self-contained timelines, assessments and
question/query/results are distributed as release evidence, outside the clean
source tree. Private connection settings and raw model request records are excluded.

## Limits and next boundary

Any app can provide the same timeline and data-only analysis interface. Meaningful
domain QA additionally needs trusted identity/state/effect producers, predicate
meanings and units, historical rules and an explicit completion contract. Bare
Datalog cannot supply missing observations. Domain contracts expose only their
declared projections; arbitrary raw JSON fields are not automatically queryable.

The current query language supports bounded joins, negation and comparisons;
arbitrary text understanding, aggregates, predictions and general causal proofs
are outside it. The checks cover exact local approval/receipt/allocation fields,
fixed quota and priority rules, literal disclosure and explicitly tagged base64.
They do not prove paraphrase-resistant information flow, external identity,
distributed consistency, continuously eligible waiting across revisions, complete
mediation or all future safety. A clean result means no observed violation under
this finite profile. These limits are part of the interface and the reported result.
