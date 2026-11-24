# Read-only trajectory viewer

```bash
policyweave inspect --traj trajectory.jsonl --connection connection.yaml
# Or open the viewer and choose a JSON/JSONL file:
policyweave inspect --connection connection.yaml
```

The viewer reads a file and serves a local page. It does not start the application,
connect to an agent, send messages, invoke tools or replay business effects.
Use the same private connection YAML as translation; the standard Inspector
workflow includes it for QA. Inspector does not require a coding CLI or running app.
Imported logs remain in memory; export returns the original data. Opening a log
replaces the selection only after validation succeeds.
**Open** lists logs explicitly registered by the server host, with a search field,
and also offers upload from the browser's device. It never browses arbitrary server
paths. Attachment-only gate files can be registered with `listed=False`.

All participants appear in one observer timeline. A directed message keeps its
actual recipients; appearing in the same timeline does not imply broadcast or
that every participant received it. A participant filter selects recorded events
involving that participant, rather than reconstructing their full model context.

## Conversation and tool log contract

Use `format: "policyscope-timeline"`, `version: 1`. This persisted format identifier is unchanged by the PolicyWeave rename. The executable validator is
`policyweave.analysis.timeline.Timeline`. See the complete
[synthetic example](../examples/trajectories/team-review.json).

```json
{
  "format": "policyscope-timeline",
  "version": 1,
  "title": "Example run",
  "roles": [
    {"id": "student", "name": "Student", "role": "Worker agent"},
    {"id": "reviewer", "name": "Reviewer", "role": "Review agent"}
  ],
  "events": [
    {
      "id": "m1",
      "sequence": 0,
      "kind": "message",
      "actor": "student",
      "recipients": ["reviewer"],
      "content": "Please review this request."
    }
  ]
}
```

This is an application-neutral **normalized format**, not an arbitrary-log
detector. Convert an application's raw JSON/JSONL into this format before import.
The viewer accepts one JSON document. It does not guess participants, recover
missing state from messages, or interpret app-specific policy meanings.

Header fields are `format`, `version`, `roles`, `events`, optional `title` and
optional `analysis` (described below).
Each participant has unique `id`, display `name`, and optional descriptive `role`.
Role labels do not authenticate identity or grant permission.

Every event requires unique `id`, contiguous integer `sequence` beginning at zero,
declared `actor`, and one of these kinds:

| Kind | Additional required fields | Meaning |
| --- | --- | --- |
| `message` | `content`, `recipients` | Recorded text and intended/recorded recipient labels |
| `tool_call` | `tool`, unique `callId`, `arguments` | Recorded tool request; arguments are JSON data |
| `tool_result` | `callId`, `result` | Result linked to one earlier call; result is JSON data |
| `llm_call` | Unique `callId`, `arguments` | Recorded model input, such as messages and model settings |
| `llm_result` | `callId`, `result` | Visible model response linked to one earlier model call |
| `state` | None | Recorded state, commonly in `data` |
| `llm_output` | `result` | Visible model output, without a required input record |
| `decision` | None | Legacy/control evidence, hidden from the default activity stream |

Optional event fields are `timestamp`, `recipients`, `content`, `tool`, `callId`,
`arguments`, `result`, and `data`. Extra application-specific fields belong inside
`data`; unknown header, participant and event fields are rejected.

Recipient IDs reference declared participants. For messages, `recipients: []`
means recipients were not recorded. Broadcast must list the recipients explicitly.
A call may have no result yet; this is shown as unrecorded, not a failure. Only one
final result per `callId` is supported; streaming chunks can be recorded as
separate messages or application data.
Tool results cannot resolve model calls, or vice versa. Model arguments and
results are data only; hidden reasoning is neither required nor reconstructed.

`Timeline.__init__` dispatches on the persisted format identifier. Conversation
logs are validated by `_observations`: declared roles/recipients, unique IDs,
contiguous order, typed event fields and matching call/result IDs. Gate logs go
through `_policy` and `TrajectorySession`, which additionally validate bindings,
rules, snapshot hashes and decision/effect consistency. Failed imports preserve
the currently selected log. Neither parser imports or executes application code.

## Replay presentation

The default stream shows agent messages, tool calls and visible model outputs.
Tool entry/return events remain distinct in the evidence but appear as one call
card in entry order. Arguments are shown first; Result is collapsed. Failed,
blocked and unfinished attempts remain recorded. Internal nested operations stay
under All events when linked by an explicit parent call ID.

`llm_output` requires a visible `result`, not model input. Older paired model
requests/responses remain readable; the output is the primary activity. Generic
Decision records do not create an additional default card. Runtime verdicts are
shown on the associated call, using its exact captured gate evidence.

Participant `kind` is explicitly agent, user, tool, environment, observer or runtime.
The sidebar defaults to agents; All events reveals other participants and their
recorded activity. Names never determine type: an agent named Runner remains an
agent. Older logs without `kind` keep their supplied participant labels rather
than acquiring guessed types. User inputs remain visible as messages.

Messages show a tag, recipients and body. A recorded send uses Message send.
An exact duplicate receipt is collapsed only with an explicit matching message ID
(or a legacy explicit parent), sender, route and content. Unmatched observations
remain visible. Timestamps remain in the export and are not displayed.

Details shows the selected activity; QA queries its captured evidence. Evidence
contains only Database. Raw inputs, rules, control records and original IDs remain
in the export for backend validation and advanced analysis; they are not additional
Evidence tabs. Viewing never invokes the recorded agents or business callbacks.

## Database

Database shows the selected call's actual recorded policy state. Before includes
the refreshed input facts and exact Request/Parameter rows. After shows confirmed
committed inputs, without carrying the expired request forward. Missing or
uncertain state remains unavailable.

Input and derived relations share one view with predicate names, argument columns
and rows. Unrecorded derived relations are marked Not recorded, never inferred to
be empty. There is no fact-search or manual derivation control. Rules remain
available to the backend for bounded QA/replay. Historical whole-log projections
are not substituted for decision-time facts.

An episode exported by the shared recorder carries native policy headers and gate
records. Inspector validates the native hashes/contracts and follows explicit
policy/call IDs. Missing or ambiguous associations stay unavailable. This does not
prove authentic identity, complete mediation or policy fidelity.

The trusted composition root can register a gate file with `register_file`, then
call `attach_gate(log_id, event_id, gate_log_id, gate_event_id)`. Both documents
must already be validated. Public import/inspection requests cannot select file
paths, follow `data.gateFile` hints, or obtain another file by naming it in a log.
Registered files are fingerprint-checked before use; original imported/exported
documents are unchanged. Unmapped events retain the historical scope.

The layout and interactions draw on the archived Nova store inspector: event
selection, before/after facts, predicate groups and read-only queries. No Nova or
Grokbot dependency is required. Distributed local-store ownership, proof trees
and action search are not inferred from a generic trajectory and are not claimed
by this frontend.

The frontend reuses the archived Grokbot UI tokens (`archive/post-mortem`,
`grokbot/packages/ui-tokens/src/tokens.css`) and its Geist Variable font from
`@fontsource-variable/geist`. Font subsets are bundled locally with their SIL
Open Font License; there is no font CDN or Node build prerequisite. The theme
control switches the same light/dark palettes. Only presentation assets and
read-only Inspector interactions are reused; the Grokbot chat composer, agent
execution controls and Nova backend are not loaded.

`timestamp` is optional and, when present, must use an ISO timestamp with seconds
and an explicit timezone, such as `2026-11-13T09:00:06.100Z`. Recorded sequence is
the default ordering, not an inferred causal order across machines. The viewer
retains event-position navigation; time is never fabricated. On opening a log,
the first visible blocked event is selected when one is recorded; otherwise the
first activity is selected. Scenario titles are used in the file picker, without
adding a scenario-specific heading to the replay screen.

Limits are 256 participants, 10,000 events, a 512 MiB trajectory file, 200,000
characters per content field, and 1 MB each for `arguments`, `result`, and `data`.
IDs are bounded to 128 characters. Content is displayed as literal text, never
HTML, code, host commands or executable connectors.
Browser file selection uploads the original bytes directly, without wrapping
and escaping the whole file in another JSON string. The backend supplies the
file limit to the browser. Existing JSON import requests remain supported with
transport headroom for escaping, and decoded evidence still has the same limit.
The CLI and registered-file reads use the same trajectory size limit.

## Existing gate trajectories

The viewer also accepts the [versioned gate contract](trajectory.md),
`policyscope-trajectory`. It validates the supplied binding, rules and fingerprints,
then presents recorded requests, decisions, callback status, results, inputs and
committed facts. Display does not invoke the native evaluator. Actor labels are
read from the recorded requests; absent conversation bodies and timestamps remain
absent.
For large monitor logs, `gate-1.json` (or another `gate-N.json` from `run.json`)
remains a focused alternative for authorization replay. Each gate file belongs
to one captured policy recorder and can contain multiple decisions; it is not a
replacement for the full conversation/tool timeline and must fit the file limit.

## Read-only analysis

Open **QA** with a mediated tool call selected. Choose **Why blocked?** or
**Why allowed?**, **Access control**, **Information flow**, or **Effects**.
These are four fixed questions, supplied by the backend. There is no editable
question field, and HTTP requests cannot supply or override the question text.
**Analysis** verifies the recorded decision by native replay and executes bounded
read-only queries against the linked gate's exact before snapshot and Request/Parameter
rows. Decision and access-control questions also query the concrete roles,
ownership or state conditions behind that verdict. The configured model proposes
supporting queries under the fixed question; the shared parser admits them and
the native engine evaluates them before the model explains the results.
The answer includes the actual verdict, supporting-query rows and event citation.
**Translation and query** reveals every query and the replay status. Selection
changes discard stale answers. These are rule-and-snapshot explanations, not
minimal proof trees or evaluator execution traces.

**Effects** uses the explicitly paired tool response and exact added/removed
facts from confirmed before/after snapshots. Missing changes remain unknown,
and permission is separate from business success. **Information flow** inspects
recorded source/dependency relations when present; absent evidence is retained as
an explicit limitation while explaining the observed access/disclosure boundary.
A blocked read cannot establish whole-run non-leakage. Missing gate evidence
requires selecting a mediated call.

Historical log queries remain available through the CLI and analysis API; they
are not a second question form in the selected-call interface. Direct Datalog
requires the native engine. The standard `--connection connection.yaml` supplies
fixed-question evidence queries and explanations through the shared model adapter. The
browser never configures credentials or contacts the model directly. The analysis
model is independent of the agents whose conversations are recorded.

Without a domain contract, conversation logs get a fixed observation vocabulary:
`Participant`, `Event`, `Recipient`, `Content`, `Omitted`, `ToolCall`, `ToolResult`,
`ModelCall`, `ModelResult`, `Timestamp`, `RecordedOutcome` and `Observed`. This supports questions about
recorded activity; it cannot infer business policies or useful task completion.
Content longer than 4,096 characters is marked omitted. The query projection is
limited to 5,000 facts, independently of the larger browsing limits.

For domain analysis, a trusted exporter can supply an optional JSON header:

```json
{
  "analysis": {
    "binding": {"...": "PolicyWeave binding with typed predicate meanings"},
    "source": "Researcher-reviewed historical analysis Datalog",
    "inputs": [{"predicate": "Predicate", "args": ["recorded", "values"]}],
    "scope": "Exactly which observations and checks this projection supports",
    "templates": [],
    "entities": {}
  }
}
```

This is a shape illustration, not an executable binding. `binding`, `source`,
`inputs` and `scope` are required; templates and entities are optional.
The domain contract replaces the default vocabulary; only its declared facts and
derived relations are queryable. Other raw event fields remain browsable. Rules
and facts are data, with no Python renderers or application imports.

Question templates retain the existing `{id, question, query}` fields and may add
`parameters` and `answer`. A parameter names an entity catalog; its placeholder is
unquoted in the query. The backend checks membership and JSON-quotes the value.
Answer wording is data-only, with plain placeholders and no functions or code:

```json
{
  "id": "recipient-events",
  "question": "Which events name this recipient?",
  "query": "?- Recipient(E,{recipient}).",
  "parameters": {"recipient": "participants"},
  "answer": {
    "en": {
      "summary": "Found {count} recorded events.",
      "row": "Event {E}.",
      "empty": "No matching recorded recipients; delivery is not inferred."
    }
  }
}
```

`entities.participants` supplies allowed values. Answer variants support `en` and
`zh`; a Chinese question selects `zh` when supplied. `summary` can reference only
`count`; `row` can reference only returned query variables; `empty` is literal.
The trusted exporter owns domain wording and its limitations. Templates without
answer wording and custom queries use a generic, evidence-scoped renderer.

The translator sees the question, schema/meanings, Datalog, scope, templates and
entity IDs. It sees neither app logic, raw fact rows nor answer wording. It selects
a template ID and parameters when possible. It can also propose a query beyond
the catalog, ask for clarification, or return unsupported. The backend
admits one read-only `?-` query using declared predicates and the existing bounded
Datalog grammar; host commands, arbitrary functions and native directives are not
query capabilities. Comparisons use `!=`, `<`, `<=`, `>` and `>=`; equality uses
shared variables or literal predicate arguments, with no `=`/`==` operator.
A prepared plan is pinned to its trajectory. The local engine
returns exact rows; a deterministic answer renderer fills the fixed summary/row
templates. This historical API/CLI workflow has no second model call to generate
the answer; its responses retain raw rows, relation-field labels and event links.
The selected-call **Analysis** workflow separately uses model explanation and a
visible **Query result** table as described above. Event links are observations,
not proof trees. No matches means no matches in the
supplied evidence, not universal safety.

`policyweave analyze timeline.json --question 'Which tools were called?'
--connection /path/to/private-connection.yaml` also supports this interface.
Existing gate logs retain the separate replay/decision QA interface described in
the [gate contract](trajectory.md).

The viewer exposes import, event selection, predefined call questions, prepared-answer
and read-only query routes; it exposes
no recorded-agent chat, application execution or mutation route. Execution in the
pilot belongs to a separate trusted sandbox service. Pinned document IDs keep
original and translated logs independent across tabs. The Python host and loopback
browser session remain trusted; do not expose a private-log server publicly.
