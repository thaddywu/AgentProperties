# SafeMA: Policy-Directed Runtime Enforcement for Agentic Applications

## Overview and Motivating Scenario

Agentic applications can send email, upload files, and modify remote state. A
bug, stale state, or incorrect decision can therefore cause an irreversible
effect even when the application was given the right safety policy.

Consider an assistant that submits recommendation letters by email or portal.
It must send Alice's letter only to a destination authorized for Alice, and
only while that request is active. The Base App may implement these checks,
but SafeMA does not rely on its internal state or reasoning.

**SafeMA enforces policy at deployer-modeled external-effect boundaries.** The
deployer identifies external API methods such as `email.send` and
`portal.submit` and declares how their actual arguments map to security
effects. SafeMA intercepts these methods at runtime and checks each effect
against trusted metadata before invoking the original API, without depending
on the Base App's internal implementation or performing application-wide taint
tracking.

## Development and Deployment Workflow

The Base App is implemented normally and remains unchanged. The deployer then
attaches three small SafeMA artifacts:

- an **API model** describing what each protected call does;
- an **origin/lifecycle model** describing where trusted metadata comes from
  and how trusted events update it; and
- a **policy** describing which normalized effects are allowed.

## System Model and Guarantee

At runtime, SafeMA intercepts a modeled call, maps its actual arguments to a
generic effect, reads current trusted metadata, and evaluates the policy before
calling the raw external API.

```text
Base App call ---> normalized Effect ---> policy ---> ALLOW ---> raw API
                         ^                   |
                         |                   +-----> DENY (no effect)
                  trusted metastore
```

For effects performed through APIs that are modeled and successfully
intercepted, the raw API is invoked only if every applicable policy allows the
normalized effect. Missing metadata and model or evaluation errors fail closed.
Unmodeled or bypassed channels are outside this guarantee.

## API Modeling Language

The API model specifies how concrete call arguments become security-relevant
operands. This excerpt from `api-effects-v1.yaml` maps the concrete
`portal.submit` method to a normalized effect:

```yaml
target:
  callable: recsub.testing.doubles.RecordingPortalAgent.submit
effect:
  kind: DISCLOSE
  resources:
    from: {select: $call.args.file_path}
    cardinality: one
    class: recommendation_letter
    identity_resolver: file_sha256
  contexts:
    from: {select: $call.args.submission_url}
    cardinality: one
    class: external_destination
  attributes:
    channel: {literal: PORTAL}
```

Thus the actual call

```python
portal.submit(file_path="bob.pdf",
              submission_url="https://portal.example.edu/alice")
```

is normalized to:

```text
DISCLOSE(
  resources  = [file identity of actual bob.pdf],
  contexts   = [actual https://portal.example.edu/alice],
  attributes = {channel: PORTAL}
)
```

Here `resources` are the objects being disclosed, while `contexts` are the
actual external destinations. The file identity contains its canonical path
and SHA-256.

## Recommendation Submission and Lifecycle

The professor or a scheduler periodically invokes the Base App. It polls
configured request sources, updates its local request records, sends deadline
reminders when no letter is ready, and submits completed PDFs by email or
through a portal automation agent that may drive a web browser:

```python
def daily_run():
    events = scan_request_sources()
    update_requests(events)

    for request in pending_requests():
        letter = find_registered_letter(request)
        if letter is None:
            continue

        if request.channel == "EMAIL":
            email.send(letter, request.destination)
        else:
            portal_agent.submit(letter, request.destination)

    send_deadline_reminders(to=professor)
```

SafeMA independently enforces both an information-flow constraint—letter and
request must have the same applicant and compatible destination—and a minimal
trusted lifecycle:

```text
             submit succeeds
ACTIVE ------------------------> SUBMITTED
   |
   | trusted cancel
   v
CANCELED
```

Cancellation comes from the configured trusted request source. Submission
changes trusted state only after the raw API returns `SUCCEEDED`. A failed
result or raised exception leaves the state `ACTIVE`, allowing a retry. These
are trusted SafeMA Context states, separate from the Base App's own
`PENDING/SUBMITTED/CANCELLED` fields; their names are model values, not
hard-coded SafeMA concepts.

## Trusted Metadata and Runtime Enforcement

SafeMA maintains a separate metastore. A professor or trusted administrative
agent registers a letter; SafeMA hashes the actual PDF and stores a trusted
resource record such as `{applicant: Alice}`. A deployment-configured trusted
request source turns `ADD`, `CANCEL`, and `REPLACE` events into request Context
records containing applicant, channel, allowed destinations, and current
state. Arbitrary Base App claims cannot create these trusted facts.

## Minimal Declarative Policy: One Portal Check

Suppose the Base App attempts this portal upload:

```python
portal.submit(file_path="bob.pdf",
              submission_url="https://portal.example.edu/alice")
```

The API model produces a `DISCLOSE` effect containing the actual Bob PDF
identity, the actual Alice portal URL, and `channel=PORTAL`. The trusted
metastore contains:

```text
resource R_bob:   identity = actual Bob PDF identity, applicant = Bob
context  C_alice: applicant = Alice, channel = PORTAL,
                  allowed_destinations = [Alice portal URL], state = ACTIVE
```

The policy first binds `$operand` to the actual PDF and finds `R_bob`, whose
identity and class match it; this record becomes `$resource`. It then iterates
over trusted request Contexts as `$context` and evaluates this YAML slice:

```yaml
exists:
  in: {select: "$metadata.contexts[*]"}
  as: context
  satisfies:
    all:
      - eq: [{select: "$context.object_class"},
             {literal: recommendation_submission_authority}]
      - eq: [{select: "$resource.attributes.applicant"},
             {select: "$context.attributes.applicant"}]
      - subset: [{select: "$effect.contexts[*].identity"},
                 {select: "$context.attributes.allowed_destinations[*]"}]
      - eq: [{select: "$effect.attributes.channel"},
             {select: "$context.attributes.channel"}]
      - eq: [{select: "$context.attributes.state"},
             {literal: ACTIVE}]
```

For `C_alice`, destination, channel, and state checks pass, but
`Bob == Alice` is false. No trusted Context satisfies every condition, so
SafeMA returns `DENY` and never invokes the raw portal API.

If the actual PDF were Alice's registered letter, every check would pass and
SafeMA would invoke the raw API. A `SUCCEEDED` return would then transition
`C_alice` from `ACTIVE` to `SUBMITTED`. If a trusted cancellation had already
changed it to `CANCELED`, or a previous submission had changed it to
`SUBMITTED`, the state check would fail and the portal upload would be denied
before the external effect.
