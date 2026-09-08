# Base App to Safe App: A Two-Minute Walkthrough

## 1. What changes?

The Base App remains unchanged. Its effectful call is still:

```python
self._email_gateway.send(message)
```

Source: [`base-app/recsub/policy.py`, line 86](../base-app/recsub/policy.py#L86)

The Safe App uses an external runner that installs SafeMA before starting the
same Base App:

```python
runtime = install(
    effect_models_path=args.effects,
    origins_path=args.origins,
    policy_path=args.policy,
    metadata_db=args.metadata_db,
)
return recsub_main(recsub_args)
```

Source: [`runner.py`, lines 38-45](runner.py#L38-L45)

`install(...)`, not import alone, replaces the YAML-configured API methods with
SafeMA wrappers. The Base App does not inherit from or implement a SafeMA class.

## 2. What does the wrapper do?

The essential path is:

```python
effect = normalize(actual_call_arguments, api_model)
decision = evaluator.evaluate(effect)

if not decision.allowed:
    raise SafeMADenied()

result = original_api(*args, **kwargs)
apply_declared_lifecycle_updates(effect, result)
```

Source: [`safema/runtime.py`, lines 134-171](../../../../safema-v1/safema/runtime.py#L134-L171)

The API model maps actual operands, such as attachments and recipients, into a
normalized `Effect`. The evaluator combines:

```text
policy YAML + actual Effect + trusted sidecar metadata
```

The YAML is an executable predicate tree. SafeMA implements only generic
operators such as `eq`, `subset`, `exists`, `all`, and `any`.

The evaluator builds the environment from the Effect and sidecar metadata at
[`safema/policy.py`, lines 61-84](../../../../safema-v1/safema/policy.py#L61-L84).
The generic operators are implemented at
[`safema/policy.py`, lines 20-51](../../../../safema-v1/safema/policy.py#L20-L51).

## 3. Minimal rejected-call demo

Assume the trusted sidecar contains:

```text
Resource:
  alice.pdf -> applicant=Alice

Context:
  applicant=Alice
  channel=EMAIL
  state=ACTIVE
  allowed_destinations={alice-submit@school.edu}
```

The buggy Base App attempts:

```python
email.send(
    to=["bob-submit@school.edu"],
    attachments=["alice.pdf"],
)
```

SafeMA derives the actual effect and evaluates the policy:

```text
registered resource                         true
resource applicant == context applicant     true
effect channel == context channel           true
context state == ACTIVE                     true
{bob@school.edu} subset of {alice@school.edu} false
```

The application-specific predicate is declared at
[`recommendation-disclosure-v1.yaml`, lines 33-47](policies/recommendation-disclosure-v1.yaml#L33-L47).

The policy evaluates to `DENY`, SafeMA raises `SafeMADenied`, and the raw email
API is never called.

If the raw API is allowed and returns `SUCCEEDED`, the declared lifecycle update
changes the trusted context from `ACTIVE` to `SUBMITTED`. A canceled or already
submitted context fails the pre-call `state == ACTIVE` predicate.

## Source pointers

- Unchanged Base App call: [`base-app/recsub/policy.py:86`](../base-app/recsub/policy.py#L86)
- SafeMA installation: [`runner.py:38`](runner.py#L38)
- Email API-to-Effect model: [`api-effects-v1.yaml:4`](models/api-effects-v1.yaml#L4)
- Application policy: [`recommendation-disclosure-v1.yaml:4`](policies/recommendation-disclosure-v1.yaml#L4)
- Runtime normalization and mediation: [`safema/runtime.py:134`](../../../../safema-v1/safema/runtime.py#L134)
- DENY before raw API: [`safema/runtime.py:161`](../../../../safema-v1/safema/runtime.py#L161)
- Raw API call after ALLOW: [`safema/runtime.py:164`](../../../../safema-v1/safema/runtime.py#L164)
- Policy evaluation: [`safema/policy.py:61`](../../../../safema-v1/safema/policy.py#L61)
- Generic `subset` implementation: [`safema/policy.py:29`](../../../../safema-v1/safema/policy.py#L29)
