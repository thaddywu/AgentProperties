# Read-only trajectory viewer

```bash
policyscope inspect trajectory.json
# Or open the viewer and choose a JSON file:
policyscope inspect
```

The viewer reads a file and serves a local page. It does not start the application,
connect to an agent, send messages, invoke tools or replay business effects.
Viewing needs no LLM, native engine, Docker or Grokbot installation.
Imported logs remain in memory; export returns the original data. Opening a log
replaces the selection only after validation succeeds.

All participants appear in one observer timeline. A directed message keeps its
actual recipients; appearing in the same timeline does not imply broadcast or
that every participant received it. A participant filter selects recorded events
involving that participant, rather than reconstructing their full model context.

## Conversation and tool log contract

Use `format: "policyscope-timeline"`, `version: 1`. The executable validator is
`policyscope.analysis.timeline.Timeline`. See the complete
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
| `state` | None | Recorded state, commonly in `data` |
| `decision` | None | Recorded decision, commonly in `data` |

Optional event fields are `timestamp`, `recipients`, `content`, `tool`, `callId`,
`arguments`, `result`, and `data`. Extra application-specific fields belong inside
`data`; unknown header, participant and event fields are rejected.

Recipient IDs reference declared participants. For messages, `recipients: []`
means recipients were not recorded. Broadcast must list the recipients explicitly.
A call may have no result yet; this is shown as unrecorded, not a failure. Only one
final result per `callId` is supported; streaming chunks can be recorded as
separate messages or application data.

`timestamp` is optional and, when present, must use an ISO timestamp with seconds
and an explicit timezone, such as `2026-11-13T09:00:06.100Z`. Recorded sequence is
the default ordering, not an inferred causal order across machines. The time
filter uses UTC and includes only timestamped events in its selected range. Logs
without timestamps retain event-position navigation; time is never fabricated.

Limits are 256 participants, 10,000 events, a 64 MiB HTTP import body, 200,000
characters per content field, and 1 MB each for `arguments`, `result`, and `data`.
IDs are bounded to 128 characters. Content is displayed as literal text, never
HTML, code, host commands or executable connectors.

## Existing gate trajectories

The viewer also accepts the [versioned gate contract](trajectory.md),
`policyscope-trajectory`. It validates the supplied binding, rules and fingerprints,
then presents recorded requests, decisions, callback status, results, inputs and
committed facts. Display does not invoke the native evaluator. Actor labels are
read from the recorded requests; absent conversation bodies and timestamps remain
absent.

## Read-only analysis

Expand **Analyze** to query the recorded evidence. Direct Datalog requires the
native engine. Add `--connection /path/to/private-connection.json` to enable
natural-language questions using the shared compatible model adapter. The
browser never configures credentials or contacts the model directly. The analysis
model is independent of the agents whose conversations are recorded.

Without a domain contract, conversation logs get a fixed observation vocabulary:
`Participant`, `Event`, `Recipient`, `Content`, `Omitted`, `ToolCall`, `ToolResult`,
`Timestamp`, `RecordedOutcome` and `Observed`. This supports questions about
recorded activity; it cannot infer business policies or useful task completion.
Content longer than 4,096 characters is marked omitted. The query projection is
limited to 5,000 facts, independently of the larger browsing limits.

For domain analysis, a trusted exporter can supply an optional JSON header:

```json
{
  "analysis": {
    "binding": {"...": "PolicyScope binding with typed predicate meanings"},
    "source": "Researcher-reviewed historical analysis Datalog",
    "inputs": [{"predicate": "Predicate", "args": ["recorded", "values"]}],
    "scope": "Exactly which observations and checks this projection supports",
    "templates": [],
    "entities": {}
  }
}
```

This is a shape illustration, not an executable binding. `binding`, `source`,
`inputs` and `scope` are required; templates and entities are optional. See a
complete generated contract in the [LabCluster pilot](study/labcluster-pilot.md).
The domain contract replaces the default vocabulary; only its declared facts and
derived relations are queryable. Other raw event fields remain browsable. Rules
and facts are data, with no Python renderers or application imports.

The translator sees the question, schema/meanings, Datalog, scope, examples and
entity IDs. It sees neither app logic nor raw fact rows. It can propose queries
beyond the examples, ask for clarification, or return unsupported. The backend
admits one read-only `?-` query using declared predicates and the existing bounded
Datalog grammar; host commands, arbitrary functions and native directives are not
query capabilities. The local engine returns exact rows with relation-field
labels and links to returned event IDs. Those links are observations, not proof
trees. No matches means no matches in the supplied evidence, not universal safety.

`policyscope analyze timeline.json --question 'Which tools were called?'
--connection /path/to/private-connection.json` also supports this interface.
Existing gate logs retain the separate replay/decision QA interface described in
the [gate contract](trajectory.md).

The viewer exposes import, event selection and read-only query routes; it exposes
no recorded-agent chat, application execution or mutation route. Execution in the
pilot belongs to a separate trusted sandbox service. Pinned document IDs keep
original and translated logs independent across tabs. The Python host and loopback
browser session remain trusted; do not expose a private-log server publicly.
