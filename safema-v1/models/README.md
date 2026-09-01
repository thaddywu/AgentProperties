# SafeMA v1 Model Declarations

This directory contains Stage 7 declarations for the frozen v1 Base App. It is
outside `v1-impl/`; the generated Base App remains unchanged.

The two YAML files intentionally describe different things:

- `api-effects-v1.yaml` describes how concrete outbound API invocations become
  normalized external effects.
- `trusted-origins-v1.yaml` describes which configured, trusted operations may
  mint or update metadata used when those effects are evaluated.

Neither file contains the policy decision itself. The initial application
policy evaluated over their outputs is conceptually:

```text
for every policy-covered resource in a DISCLOSE effect:
    resource.principal == destination_context.principal
    AND destination_context.state == active
    AND actual_destinations is a subset of allowed_destinations
```

The SafeMA core must not contain the terms `recommendation_letter`, `applicant`,
`EMAIL`, or `PORTAL` as hard-coded cases. They are declaration values in this
application-specific model package.

## Reading `api-effects-v1.yaml`

Read each model from top to bottom:

1. `target.callable` is the concrete Python method patched by the runtime.
2. `bind.strategy: inspect_signature` means positional and keyword arguments
   are first bound to their declared Python parameter names.
3. `effect.kind` and `effect.channel` add constant semantic attributes.
4. `resources` selects the artifacts affected by the call.
5. `destinations` selects the external recipients or target contexts.
6. `correlation` preserves an application correlation value for audit; it is
   not itself trusted identity metadata.

Selectors use a small, read-only path notation:

- `$receiver` is the method receiver (`self`).
- `$call.args.NAME` is a signature-bound argument.
- `$return` is a successful return value.
- `$item` is the current element of an event stream.
- `[*]` selects every element of a sequence.
- `union` concatenates selected sets; it does not decide whether equality or
  subset membership is required. That is a policy decision.

For the email model, To and CC are simply normalized as the actual destination
set. The Effect Model does not say that CC is forbidden. The current policy and
trusted destination context determine whether those actual recipients are
allowed.

The email model declares every attachment position in this Base App's gateway
to contain a policy-covered recommendation-letter resource. An empty attachment
sequence, such as a reminder, produces no covered file resources. A selected
attachment that cannot be resolved through `registered_file_v1` is an
interpretation failure and is denied before the raw call. This classification
is specific to the frozen Recommendation Submission System; a general email
application would need a different resource-classification declaration.

## Normalized effects

The email declaration produces an object equivalent to:

```yaml
kind: DISCLOSE
channel: EMAIL
correlation: REQ-000001
resources:
  - resource_ref: /absolute/path/to/letter.pdf
    resource_class: recommendation_letter
destinations:
  - admissions@example.edu
```

The portal declaration produces the same normalized shape with `channel:
PORTAL`, a file selected from the portal call, and the portal URL as its single
destination.

These examples show normalized data only. They do not imply an allow or deny
decision.

## Reading `trusted-origins-v1.yaml`

The letter-registration origin is observed only after the Base App operation
returns successfully. It records an immutable resource version using both a
canonical path and a SHA-256 content fingerprint. A later same-path content
change therefore fails resource resolution instead of silently inheriting the
old binding.

The request-source origins are trusted only because deployment configuration
places the concrete adapters and their backing mock world in the trusted
computing base. SafeMA consumes their normalized events directly. It does not
mint destination bindings from values later read from the Base App's SQLite
database.

`ADD_REQUEST`, `CANCEL_REQUEST`, and `REPLACE_REQUEST` respectively activate,
deactivate, and atomically replace destination contexts. Purpose is retained as
an auxiliary claim for possible later policies, but the first SafeMA policy
subset does not evaluate it.

## Current concrete targets

The outbound targets are the actual local doubles used by the executable Base
App configuration:

- `recsub.testing.doubles.RecordingEmailGateway.send`
- `recsub.testing.doubles.RecordingPortalAgent.submit`

The trusted metadata origins are:

- `recsub.service.Application.register_letter`
- `recsub.testing.doubles.JsonFileRequestSource.scan`
- `recsub.testing.doubles.ScriptedRequestSource.scan`

A real email gateway, portal agent, or request-source adapter requires a new
target declaration. Adding a target does not require changing the SafeMA core.

## Failure semantics

Interpretation occurs before the raw outbound API call. When a model-selected,
policy-covered resource requires metadata and cannot be resolved, or when a
required selector cannot be evaluated, the decision is `DENY`. A denied call
must not invoke the saved raw callable.

Calls through APIs without registered models remain outside the SafeMA v1
guarantee boundary.
