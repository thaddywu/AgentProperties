# Recommendation Submission System — version 1

A local, single-user command-line application for a professor who manages
several outstanding recommendation requests. It records requests received from
external sources, records completed letters the professor wrote outside the
application, matches letters to compatible requests, submits them by email or
through a recommendation portal, sends deadline reminders, and keeps the
result history.

The application never writes, edits, summarizes, or inspects letter content.
It stores a *reference* to each letter file and hands that file to an external
component when — and only when — the Safety Policy permits the disclosure.

Implements `app-spec-v1.md` (behavior) and `policy-v1.md` (permitted external
effects).

---

## Requirements

* Python 3.11 or newer (developed on 3.13). Only the standard library is used.
* `pytest` to run the test suite.

No external database server is needed; the application keeps everything in one
local SQLite file.

## Layout

```
recsub/
  cli.py           the command-line interface
  service.py       the core operations (ingest, register, cancel, match, submit, remind)
  policy.py        the Safety Policy guard — the ONLY caller of external components
  messages.py      plain-text subject/body builders (text only, no recipients)
  repository.py    all SQLite reads and writes
  db.py            schema and connection management
  config.py        configuration loading, validation, component construction
  interfaces.py    the external interfaces (request source, email, portal, clock)
  models.py        value objects and stored-record types
  validation.py    validation of everything arriving from outside
  timeutil.py      RFC 3339 parsing and UTC storage format
  enums.py         the fixed version-1 enumerations
  errors.py        the error types
  testing/         deterministic local test doubles for every interface
tests/             the automated test suite
examples/          a runnable configuration, sample events, and an adapter template
```

### Where the Safety Policy is enforced

Every external disclosure goes through `PolicyGuard` in
[recsub/policy.py](recsub/policy.py). Nothing else in the package calls the
email gateway or the portal agent.

The guard does not trust its caller. For each disclosure it re-reads the
authoritative request and letter records from the database, re-checks all the
conditions of policy section 5 against that state, and then *builds* the
outbound message itself — the recipient comes from the request's own recorded
destination, the attachment from the letter's own registered path, and the
channel from the request's own recorded channel. A caller cannot supply a
recipient, a URL, or a file of its own. If any condition fails, the guard
raises `PolicyViolation` and makes no external call at all; the application
records that as a failed attempt and carries on with the rest of the batch.

Reminders take the same route: they are addressed only to the configured
professor address, carry no CC and no attachment, and are refused for a
`SUBMITTED` or `CANCELLED` request.

---

## Configuration

Configuration is one JSON or TOML file. Nothing operational is hard-coded.

```json
{
  "database_path": "recsub.sqlite3",
  "professor_email": "professor@example.edu",
  "display_time_zone": "America/New_York",

  "request_sources": [
    {
      "factory": "recsub.testing.doubles:json_file_request_source",
      "options": { "source_kind": "email_inbox", "events_path": "events.json" }
    }
  ],
  "email_gateway": {
    "factory": "recsub.testing.doubles:recording_email_gateway",
    "options": { "log_path": "outbound.jsonl" }
  },
  "portal_agent": {
    "factory": "recsub.testing.doubles:recording_portal_agent",
    "options": { "log_path": "outbound.jsonl" }
  },
  "clock": {
    "factory": "recsub.testing.doubles:fixed_clock",
    "options": { "instant": "2026-11-01T12:00:00Z" }
  }
}
```

| Key | Meaning |
| --- | --- |
| `database_path` | the SQLite file the application owns |
| `professor_email` | the only address a deadline reminder may be sent to |
| `display_time_zone` | IANA zone used for human-readable output |
| `request_sources` | zero or more request-source agents; each must declare a distinct `source_kind` |
| `email_gateway` | the component that sends ordinary email |
| `portal_agent` | the component that performs portal submissions |
| `clock` | optional; defaults to `recsub.interfaces:system_clock` |

A component is named as `package.module:callable`. The callable is invoked with
its `options` as keyword arguments and must return an object implementing the
matching interface; every component is type-checked against its interface at
startup. Relative paths — `database_path` and any option key ending in `_path`
— are resolved against the directory holding the configuration file.

Pass the file with `--config PATH` or set `RECSUB_CONFIG`. Validate it with:

```bash
python -m recsub --config config.json check-config
```

Missing keys, an unparsable address, an unknown time zone, a factory that
cannot be imported, and a component that does not implement its interface are
each reported as a configuration error with exit code 2.

## Initializing the database

```bash
python -m recsub --config config.json init-db
```

This creates the file and its schema. It is idempotent, and every other
command creates the schema too if it is absent — so `init-db` is a convenience
rather than a required first step.

---

## Command-line operations

All commands take the global flags `--config PATH` and `--json` (machine-readable
output). Exit codes: `0` success, `1` an application error, `2` a usage or
configuration error.

| Command | What it does |
| --- | --- |
| `check-config` | validate the configuration and build every component |
| `init-db` | create the SQLite database and its schema |
| `sync` | scan every configured request source and apply the events returned |
| `register-letter --path P --applicant NAME --purpose PURPOSE` | register one completed letter file |
| `cancel-request REQUEST_ID` | cancel one `PENDING` request |
| `process` | attempt one submission for each pending request that has a compatible letter |
| `remind` | send the deadline reminders that are due |
| `daily-run` | `sync`, then `process`, then `remind`, in that order |
| `list-requests [--status STATUS]` | list requests, optionally filtered |
| `show-request REQUEST_ID` | full stored detail plus submission and reminder history |
| `list-letters` | list registered letters |
| `list-submissions` | list every submission attempt with receipts and errors |
| `list-reminders` | list every reminder attempt |

### A worked example

```bash
python -m recsub --config config.json init-db
python -m recsub --config config.json sync

python -m recsub --config config.json register-letter \
    --path letters/ada-phd.pdf \
    --applicant "Ada Lovelace" \
    --purpose PHD_APPLICATION

python -m recsub --config config.json process
python -m recsub --config config.json remind

python -m recsub --config config.json list-requests
python -m recsub --config config.json show-request REQ-000004
```

`examples/` holds a configuration and an event file that run exactly this way
against the local doubles:

```bash
mkdir -p /tmp/recsub-demo/letters && cd /tmp/recsub-demo
cp <repo>/examples/config.example.json <repo>/examples/events.example.json .
echo 'letter' > letters/ada-phd.pdf
PYTHONPATH=<repo> python -m recsub --config config.example.json daily-run
```

Everything the doubles were asked to send is appended to `outbound.jsonl`.

### The daily run

`daily-run` is meant to be launched by an external scheduler — the application
is not a scheduling daemon. For 12:00 noon local time:

```cron
0 12 * * *  cd /home/professor/recsub && /usr/bin/python3 -m recsub --config config.json daily-run >> daily.log 2>&1
```

The three stages are independent: a request source that raises still lets the
other sources' events through, a failed submission still leaves the remaining
requests to be attempted, and a stage that fails outright is reported while the
later stages still run.

---

## Behavior worth knowing

**Requests are immutable.** If an external deadline, destination, purpose, or
description changes, the source agent returns one `REPLACE_REQUEST` event. The
old request becomes `CANCELLED`, a new `PENDING` request is created, and the
supersession is recorded — all in one transaction. If any part of the event is
invalid, the whole event is rejected and nothing changes.

**Repeated scans are safe.** Each event carries a stable event ID. An event ID
already applied is ignored, and an add event whose source reference is already
ingested is ignored as a duplicate.

**Deadlines need an explicit offset.** `2026-12-01T23:59:00-05:00` and
`2026-12-02T04:59:00Z` are both accepted and stored as the same UTC instant.
A bare date is rejected.

**Matching is exact.** A letter matches a request only when the canonical
applicant names are exactly equal (case-sensitive, after trimming) and the
purposes are equal. Filenames, file contents, descriptions, destinations, and
deadlines play no part. When several letters match, the most recently
registered wins; equal timestamps are broken by the greater letter ID.

**Letters are reusable.** One `PHD_APPLICATION` letter serves every
`PHD_APPLICATION` request for that applicant. A successful submission does not
consume it.

**Registered files are immutable.** Save a revision at a new path and register
it again; that produces a new letter ID. If a registered file has disappeared
at submission time, the attempt is recorded as failed and no external
component is called.

**Failures are retryable, terminal states are not.** A `FAILED` submission
leaves the request `PENDING` for a later run. `SUBMITTED` and `CANCELLED` are
terminal and are never processed again. Passing a deadline changes nothing by
itself.

**Reminders.** Only a pending request with a future deadline and no compatible
letter qualifies. More than 24 and up to 72 hours out gives a `THREE_DAY`
reminder; 24 hours or less gives a `ONE_DAY` reminder, which takes precedence.
Each kind succeeds at most once per request; a failed attempt may be retried
while the request is still in the window.

**Record IDs** are `REQ-000001`, `LET-000001`, `SUB-000001`, `REM-000001` —
zero-padded so that sorting them as text matches the order they were created.

---

## Running the tests

From the repository root:

```bash
python -m pytest
```

The suite runs entirely locally against the deterministic doubles in
`recsub/testing/`; no network, no real service, no wall-clock dependence
(a `FixedClock` drives every time-sensitive test).

| File | Covers |
| --- | --- |
| `tests/test_validation.py` | deadlines, applicant names, destinations, purposes, event shapes |
| `tests/test_ingest.py` | add/cancel/replace events, deduplication, per-event and per-agent isolation |
| `tests/test_letters.py` | registration rules and the matching rules |
| `tests/test_processing.py` | cancellation, email and portal submission, batch resilience, reuse |
| `tests/test_reminders.py` | reminder windows, qualification, at-most-once-per-kind |
| `tests/test_policy.py` | the Safety Policy: every forbidden disclosure, checked at the guard |
| `tests/test_daily_run.py` | stage order and resilience of the daily run |
| `tests/test_persistence.py` | durability, transactional consistency, schema constraints |
| `tests/test_config.py` | configuration validation and component construction |
| `tests/test_cli.py` | every command end to end through `main()` |

---

## Providing real external adapters

Copy `examples/adapters_template.py`, fill in the bodies, and point the
configuration at your factories. There are four interfaces, all defined as
protocols in [recsub/interfaces.py](recsub/interfaces.py) — you only need the
listed methods, not a base class.

### `RequestSource`

```python
@property
def source_kind(self) -> str: ...
def scan(self) -> Sequence[RequestEvent]: ...
```

`scan` returns normalized events; the agent does the parsing, and the core
application never sees email prose or portal HTML. An event is:

```python
RequestEvent(
    event_id="inbox-0001",        # stable for this external change
    source_kind="email_inbox",    # must equal the agent's own source_kind
    kind="ADD_REQUEST",           # or CANCEL_REQUEST / REPLACE_REQUEST
    new_request=NewRequest(       # for ADD_REQUEST and REPLACE_REQUEST
        source_reference="message-0001",
        applicant_name="Ada Lovelace",
        application_description="MIT EECS PhD application",
        purpose="PHD_APPLICATION",         # or FELLOWSHIP
        channel="EMAIL",                   # or PORTAL
        destination="phd-admissions@example.edu",  # an address, or an https URL
        deadline="2026-12-01T23:59:00-05:00",      # RFC 3339 with an offset
    ),
    target_source_reference=None, # the old request, for CANCEL / REPLACE
    target_source_kind=None,      # defaults to source_kind
)
```

An equivalent plain `dict` with the same keys is also accepted. Returning the
same events on later scans is expected and safe.

### `EmailGateway`

```python
def send(self, message: EmailMessage) -> ExternalResult: ...
```

`message` carries `to`, `cc`, `subject`, `body`, `attachments` (absolute paths
to existing files) and `correlation_id` (the request ID, for your logs).

### `PortalAgent`

```python
def submit(self, *, correlation_id: str, submission_url: str,
           file_path: str) -> ExternalResult: ...
```

Report `SUCCEEDED` only after observing an explicit portal confirmation.

### `Clock`

```python
def now(self) -> datetime: ...   # must be timezone-aware
```

### Rules every adapter must follow

* **Return data; never touch the database.** The application owns its SQLite
  file. Adapters communicate only through arguments and return values.
* **Translate your own failures.** Return
  `ExternalResult.failed("SMTP_TIMEOUT", "…")` rather than raising. An adapter
  that raises anyway is recorded as a failed attempt with error code
  `ADAPTER_EXCEPTION`, and an adapter that returns something that is not an
  `ExternalResult` is recorded as `INVALID_ADAPTER_RESULT`; in both cases the
  request stays `PENDING` and the batch continues.
* **Only report success when the external system confirmed it.** Version 1 has
  no ambiguous outcome: `SUCCEEDED` moves the request to `SUBMITTED` for good.

One integration may implement several interfaces — a portal integration can be
both a `RequestSource` and a `PortalAgent`. Register it once per role in the
configuration.
