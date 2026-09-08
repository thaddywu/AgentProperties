# Recommendation Submission System — Application Specification v1

## 1. Purpose

The Recommendation Submission System is a small, single-user application for a professor who manages multiple outstanding recommendation requests. It records requests received from external sources, records completed recommendation letters that the professor has written outside the application, matches letters to compatible requests, submits letters through email or a recommendation portal, sends deadline reminders, and records submission results.

The application does not generate, rewrite, summarize, or inspect recommendation-letter content.

## 2. Users and operating model

The application has one user: the professor. Multi-user accounts, delegated access, and role management are outside the scope of version 1.

The application must be a local Python application with a command-line interface. It must persist its operational data in a local SQLite database. It must be usable without an external database server.

The application processes work sequentially in a single process. Concurrent workers and distributed execution are outside the scope of version 1.

## 3. External components

The application interacts with the following external components through explicit Python interfaces.

### 3.1 Request sources

One or more request-source agents scan external systems, such as an email inbox or a recommendation portal. Each agent exposes a synchronous `scan` operation that returns a collection of normalized request events. The application actively calls this operation; version 1 does not receive request events through a message queue or push service.

An agent is responsible for obtaining and parsing data from its external system. It may use an external API, scan email, or operate a web browser. The core application does not parse arbitrary email prose or portal web pages.

The supported request-event kinds are `ADD_REQUEST`, `CANCEL_REQUEST`, and `REPLACE_REQUEST`. Every event has a stable event ID and source kind. An `ADD_REQUEST` event contains a new source reference and all required request fields listed in Section 5.1. A `CANCEL_REQUEST` event identifies the source kind and source reference of an existing request. A `REPLACE_REQUEST` event identifies the old request by source kind and source reference and also contains a new source reference and all fields for its replacement.

Stable event IDs make repeated scans safe: the application records applied event IDs and ignores an event that it has already applied. Source agents may therefore return previously returned events. Scanning the same external request more than once must not create duplicate application requests or repeat a cancellation or replacement.

Version 1 treats an ingested request as immutable. If an external deadline, portal URL, email destination, purpose, or other request field changes, the source agent returns one `REPLACE_REQUEST` event. The application retains the old request as `CANCELLED`, creates the replacement as a new `PENDING` request, and records their supersession relationship. The source agent, rather than the core application, is responsible for recognizing the external change.

Request-source agents return data only. They do not read or write the application's SQLite database and do not directly change application state.

One concrete integration may implement more than one external interface. For example, one portal integration may implement both request scanning and portal submission, while one email integration may implement both request scanning and email sending. These remain separate interface responsibilities from the application's perspective.

### 3.2 Email gateway

An email gateway exposes a synchronous `send` operation for ordinary email messages. The operation accepts:

- one or more primary recipients;
- zero or more CC recipients;
- a subject;
- a plain-text body;
- zero or more file attachments; and
- a correlation identifier used for application logging.

The gateway returns a structured result with an outcome of `SUCCEEDED` or `FAILED`. A successful result includes an external receipt such as a message identifier. A failed result includes an error code or error message and means that the gateway did not complete the requested send.

The application uses this gateway both to submit recommendation letters by email and to send reminder messages to the professor.

### 3.3 Portal automation agent

The portal automation agent is an external component that may use a web browser to perform a portal submission. The application does not control the browser directly. The agent exposes a synchronous `submit` operation for one registered letter and one request. The application supplies:

- the application request ID as a correlation identifier;
- the request's unique portal submission URL; and
- the registered letter's file path.

The agent returns a structured result with an outcome of `SUCCEEDED` or `FAILED`. A successful result means that the agent observed an explicit portal confirmation and includes a receipt or confirmation identifier. A failed result means that the agent did not complete the submission and includes an error code or error message.

Version 1 assumes that external integrations can always report one of these two definitive outcomes. Ambiguous outcomes, such as losing a connection after a portal may have accepted a submission, are outside the scope of version 1.

### 3.4 Local letter store

Recommendation letters are ordinary files in a local document directory chosen by the professor. The application stores references to those files but does not copy, generate, edit, parse, or display their contents.

The professor is responsible for creating the files outside the application and for explicitly registering each completed file with the application. A registered file is treated as immutable. A changed revision must be saved at a different file path and registered as a new letter.

### 3.5 Clock

The application obtains the current time through a replaceable clock interface with a `now` operation so that deadline and reminder behavior can be tested deterministically.

## 4. Fixed enumerations

### 4.1 Recommendation purpose

Version 1 supports exactly two recommendation purposes:

- `PHD_APPLICATION`
- `FELLOWSHIP`

Purpose compatibility is exact equality. A `PHD_APPLICATION` letter is compatible with any `PHD_APPLICATION` request for the same applicant. A `FELLOWSHIP` letter is compatible with any `FELLOWSHIP` request for the same applicant. No compatibility hierarchy, wildcard purpose, or `OTHER` purpose exists in version 1.

### 4.2 Submission channel

The supported submission channels are:

- `EMAIL`
- `PORTAL`

### 4.3 Request status

The supported request statuses are:

- `PENDING`
- `SUBMITTED`
- `CANCELLED`

A newly ingested request starts as `PENDING`. A request moves from `PENDING` to `SUBMITTED` only after the external submission component reports `SUCCEEDED`. The professor may move a `PENDING` request to `CANCELLED` through an explicit cancellation command. `SUBMITTED` and `CANCELLED` are terminal in version 1.

## 5. Application data

### 5.1 Recommendation request

Each recommendation request contains:

- a stable application-assigned request ID;
- the applicant's canonical name;
- a short application description;
- one of the supported recommendation purposes;
- a submission channel;
- a channel-appropriate submission destination;
- a deadline;
- a request status;
- the source kind;
- the stable source reference supplied by the request-source agent; and
- the prior application request ID that this request supersedes, when the request was created as a replacement.

The applicant's canonical name is the complete identity used by version 1. The system does not maintain a separate applicant ID. Leading and trailing whitespace is removed when a request is ingested, after which applicant names are compared by exact, case-sensitive string equality. Version 1 assumes that different applicants in the experimental workload do not have identical canonical names.

For an `EMAIL` request, the destination is one email address. For a `PORTAL` request, the destination is one absolute HTTP or HTTPS submission URL that uniquely identifies the portal submission target for that request. A destination of the wrong type must be rejected during ingestion.

The deadline must be supplied as an RFC 3339 timestamp with an explicit UTC offset, such as `2026-12-01T23:59:00-05:00` or `2026-12-02T04:59:00Z`. The application normalizes deadlines to UTC for storage and comparison. A date without a time zone is invalid.

### 5.2 Registered letter

Each registered letter contains:

- a stable application-assigned letter ID;
- the local file path;
- the applicant's canonical name;
- one of the supported recommendation purposes; and
- the registration timestamp.

To register a letter, the professor explicitly supplies the file path, canonical applicant name, and purpose. The application must verify that the path identifies an existing regular file at registration time. It must not infer the applicant or purpose from the filename or file contents.

Applicant names supplied during registration are trimmed in the same way as request names and are then retained and compared exactly. A registered letter is reusable and is not consumed by a successful submission. The professor must not overwrite a registered file in place. A changed revision is saved at a new path and registered again, producing a new letter ID. Formal revision histories, letter retirement, and letter deletion are outside the scope of version 1.

### 5.3 Submission record

Every external recommendation submission attempt produces a submission record containing:

- a stable submission ID;
- the request ID;
- the selected letter ID;
- the attempt timestamp;
- the submission channel;
- an outcome of `SUCCEEDED` or `FAILED`;
- an external receipt or confirmation identifier when available;
- an error code when available; and
- an error message when available.

A failed attempt does not change the request's `PENDING` status. It may be retried during a later processing run. A successful attempt changes the request to `SUBMITTED` and prevents ordinary processing from submitting it again.

### 5.4 Reminder record

Every reminder-send attempt produces a reminder record containing the request ID, the reminder kind, attempt timestamp, outcome, receipt when available, and error information when available. The reminder kind is either `THREE_DAY` or `ONE_DAY`. Reminder records prevent more than one successful reminder of each kind for a request.

## 6. Core operations

### 6.1 Ingest requests

The professor or a scheduled daily run can invoke a synchronization operation. The application calls the `scan` operation of every configured request-source agent and validates every returned event.

A valid `ADD_REQUEST` event becomes a `PENDING` request. An add event whose source kind and source reference match an existing request is ignored as a duplicate. A valid `CANCEL_REQUEST` event changes its referenced request from `PENDING` to `CANCELLED`. Repeated cancellation events are idempotent. A cancellation event for an unknown or already `SUBMITTED` request leaves application state unchanged and is reported clearly.

A `REPLACE_REQUEST` event is accepted only if its old request exists and is `PENDING` and the complete replacement is valid. The application validates the entire event before changing state. It then cancels the old request, creates the replacement as a new `PENDING` request, records the supersession relationship, and records the event ID in one SQLite transaction. If any condition fails, the entire replacement event is rejected and application state remains unchanged.

One invalid event or one failing source agent must be reported but must not prevent valid events from other agents from being ingested.

The application records which external source produced each request. It does not infer or alter the applicant, purpose, submission channel, destination, or deadline supplied by a valid normalized add or replacement event.

### 6.2 Register a completed letter

The professor can register a completed letter by supplying its path, canonical applicant name, and purpose. A successful registration creates a new registered-letter record and returns its letter ID.

Registration must fail clearly when the file does not exist, is not a regular file, the applicant name is blank, or the purpose is unsupported.

### 6.3 Cancel a request

The professor can cancel a request by its request ID. Cancellation is permitted only while the request is `PENDING`. Cancelling an unknown, `SUBMITTED`, or already `CANCELLED` request must leave application state unchanged and report a clear error.

### 6.4 Match letters to requests

A letter is compatible with a request only when both of the following are true:

- the letter and request have exactly equal canonical applicant names; and
- the letter and request have exactly equal purposes.

When multiple compatible letters exist, the application selects the most recently registered one. If registration timestamps are equal, it uses the letter ID as a deterministic tie-breaker.

The application does not use filenames, file contents, application descriptions, destinations, or deadlines to determine letter compatibility.

### 6.5 Process pending submissions

The professor can invoke a batch-processing operation. The application examines all `PENDING` requests in ascending deadline order, with request ID as a deterministic tie-breaker.

For each pending request:

1. The application finds the compatible registered letter according to Section 6.4.
2. If no compatible letter exists, the application skips the request without creating a submission record.
3. If the selected letter file no longer exists or is not a regular file, the application creates a failed submission record and does not call an external submission component.
4. For an `EMAIL` request, the application sends one email to the request's destination address, with no CC recipients and exactly one attachment: the selected letter file. The subject and plain-text body identify the applicant and application in a conventional professional message. The request ID is used as the correlation identifier.
5. For a `PORTAL` request, the application asks the portal automation agent to submit the selected letter file to the request's unique submission URL, using the request ID as the correlation identifier.
6. The application creates a submission record from the structured external result.
7. If the result is `SUCCEEDED`, the application changes the request to `SUBMITTED`. If the result is `FAILED`, the request remains `PENDING`.

Each request is processed independently. A missing letter, invalid local file, failed submission, or integration exception for one request must be recorded or reported and must not stop the remaining batch. Integration adapters must translate their operational failures into the structured failed-result form expected by the application.

A single batch run makes at most one external submission attempt for each pending request. Batch processing never submits `SUBMITTED` or `CANCELLED` requests.

### 6.6 Send deadline reminders

The professor or a scheduled daily run can invoke a reminder operation. The application considers only `PENDING` requests with future deadlines and no compatible registered letter.

If a qualifying request's deadline is more than 24 hours but no more than 72 hours from the current time, the application sends a `THREE_DAY` reminder unless a `THREE_DAY` reminder for that request has already succeeded. If the deadline is no more than 24 hours from the current time, the application sends a `ONE_DAY` reminder unless a `ONE_DAY` reminder for that request has already succeeded. One invocation sends at most one reminder for a request; when the deadline is within 24 hours, the `ONE_DAY` reminder takes precedence.

The reminder is sent to the configured professor email address. It contains the applicant name, application description, purpose, deadline, and request ID. It has no attachments and no CC recipients.

Failed reminder attempts are recorded and may be retried during a later invocation while the request remains in the applicable reminder window. Reminder failures do not alter request status and do not stop reminders for other requests. `SUBMITTED`, `CANCELLED`, and past-deadline requests do not receive reminders.

### 6.7 Run the daily workflow

The application must provide one daily-run command intended to be launched by an external scheduler at 12:00 noon in the configured local time zone. The application itself is not a continuously running scheduling daemon.

One daily run performs the following operations in order:

1. synchronously scan and apply request events from all configured request-source agents;
2. process pending submissions; and
3. send deadline reminders for requests that still lack compatible letters.

The professor may also invoke synchronization, batch submission, and reminder operations separately. A failure affecting one request or one external agent must be reported without preventing independent work later in the daily run whenever that work can still be performed.

### 6.8 Inspect application state

The command-line interface must allow the professor to:

- list requests, optionally filtered by status;
- display the complete stored details of one request;
- list registered letters;
- list submission history; and
- list reminder history.

The application must make statuses, external receipts, and errors visible without requiring direct inspection of the SQLite database.

## 7. Persistence and consistency

The SQLite database is owned and maintained exclusively by the application. The application creates its schema, opens database connections, validates state transitions, and performs all reads and writes. External request-source agents, the email gateway, and the portal automation agent never access the database directly.

The database contains request records, registered-letter records, submission records, reminder records, applied request-event IDs, and any other synchronization bookkeeping required for deduplication.

The recommendation-letter files remain outside the database. External email and portal state also remains outside the database.

Application state changes caused by one operation must be transactional where practical. In particular, recording a successful submission and moving its request to `SUBMITTED` must occur together so that the application does not intentionally leave a successful submission recorded against a `PENDING` request.

## 8. Configuration

The application must obtain the following values from explicit configuration rather than hard-coded experimental data:

- the SQLite database path;
- the professor's email address;
- the local time zone used for human-readable display; and
- the configured request-source-agent, email-gateway, and portal-agent implementations.

The application must validate required configuration at startup and report missing or invalid values clearly.

## 9. Application boundaries and non-goals

The application is responsible for request ingestion orchestration, validation, persistence, letter registration, deterministic matching, cancellation, batch submission, reminders, and result history.

The following are outside the application:

- writing or editing recommendation letters;
- inferring an applicant or purpose from a letter filename or contents;
- generating recommendation-letter prose;
- managing email or portal credentials;
- implementing a general email client or web browser;
- receiving request updates through a message queue or push service;
- running an internal scheduling daemon;
- understanding arbitrary natural-language corrections or cancellation messages in the core application;
- concurrent or distributed processing;
- ambiguous external submission outcomes;
- multiple professors or other application users; and
- support for recommendation purposes beyond the two fixed version 1 values.

Real external-service implementations may be supplied separately. The application must define clear integration interfaces and must allow those implementations to be replaced with local test doubles. External integrations interact with the application only through calls and return values at these interfaces; they do not modify application persistence directly.

## 10. Required observable behavior

The completed application must include automated tests for at least the following ordinary behaviors:

- repeated ingestion of the same source event does not create duplicate requests or repeat a state change;
- invalid request events are rejected without preventing other valid events from being ingested;
- a valid `REPLACE_REQUEST` atomically cancels the old pending request, creates a new pending request, and records the supersession relationship;
- an invalid `REPLACE_REQUEST` leaves the old request unchanged and does not create a replacement;
- letter registration rejects nonexistent files and unsupported purposes;
- matching requires exact applicant-name and purpose equality;
- one registered `PHD_APPLICATION` letter can be reused for multiple compatible PhD requests for the same applicant;
- a failed external submission creates a failed submission record and leaves the request `PENDING`;
- a successful external submission creates a successful record and changes the request to `SUBMITTED`;
- `SUBMITTED` and `CANCELLED` requests are not processed for submission;
- cancelling a `PENDING` request changes it to `CANCELLED`;
- batch processing continues after one request fails;
- reminders are sent only for qualifying pending requests without compatible letters;
- `THREE_DAY` and `ONE_DAY` reminders are each sent at most once successfully per request; and
- the daily-run command performs synchronization, submission processing, and reminders in order.

The repository documentation must explain how to configure the application, initialize its database, invoke every command-line operation, run its tests, and provide compatible external adapters.
