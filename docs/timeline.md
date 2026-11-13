# Read-only trajectory viewer

```bash
policyscope inspect trajectory.json
# Or open the viewer and choose a JSON file:
policyscope inspect
```

The viewer reads a file and serves a local page. It does not start the application,
connect to an agent, send messages, invoke tools, configure a model, or replay
business effects. No LLM, native engine, Docker or Grokbot installation is required.
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

Header fields are `format`, `version`, `roles`, `events`, and optional `title`.
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

The separate `policyscope analyze` command retains replay and optional NL QA APIs.
The viewer does not call them and exposes no chat, model, tool-execution or
application-mutation route. Its only POST operations import data and select a
recorded event. The Python host and loopback browser session remain trusted; do
not expose a private-log server publicly.
