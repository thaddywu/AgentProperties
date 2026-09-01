# SafeMA v1 concrete execution trace

This trace uses the deterministic `wrong_email_destination` treatment run in
`results-v1.json`. The fault is explicit: after the trusted request-source
event has been ingested, the Base App's own `requests.destination` row is
changed from Alice's authenticated destination to a different, syntactically
valid address. The frozen Base App is not modified.

## 1. Trusted metadata is minted

1. `ScriptedRequestSource.scan()` returns `EVENT-001` from trusted source
   `trusted-world`. Its authenticated claims are:

   ```text
   source_reference = WORLD-REQ-001
   principal        = Alice
   channel          = EMAIL
   destination      = alice-submit@example.edu
   purpose          = PHD_APPLICATION
   ```

2. The origin declaration at `models/trusted-origins-v1.yaml:120` selects the
   scripted source. The wrapper at `safema/runtime.py:199` first lets `scan()`
   return, then observes its returned events. `ADD_REQUEST` activates this
   sidecar row:

   ```text
   context_key         = ["trusted-world","WORLD-REQ-001"]
   principal           = Alice
   channel             = EMAIL
   allowed_destinations= ["alice-submit@example.edu"]
   state               = active
   ```

   The `1` in `metadata_active_contexts = 1` is a row count over active
   `destination_contexts`; it is not supplied by the Base App.

3. `Application.register_letter(...)` returns Base App ID `LET-000001`. The
   origin model at `trusted-origins-v1.yaml:6` runs only after that successful
   return. The runtime calls `bind_resource()` at `safema/runtime.py:229`, and
   the sidecar stores:

   ```text
   binding_id          = 1
   resolver_id         = registered_file_v1
   resource_class      = recommendation_letter
   principal           = Alice
   application_letter_id = LET-000001
   purpose             = PHD_APPLICATION
   fingerprint         = adbc61a611d2daccba2b7e9a26204a8b638ac63b945604e0f9f4a3baed757aa3
   ```

   `binding_id = 1` is SQLite's first autoincrement sidecar binding. The digest
   is SHA-256 of the exact fixture bytes
   `deterministic Alice recommendation v1\n`, computed by
   `safema/registry.py:70-76`.

## 2. The ordinary Base App call is intercepted

The fault changes only the Base App row to:

```text
requests.request_id  = REQ-000001
requests.destination = mallory-submit@example.edu
```

The native guard consequently constructs a message to that address. The exact
unchanged application line is:

```python
# v1-impl/recsub/policy.py:86
return self._call(lambda: self._email_gateway.send(message))
```

At startup, `SafeMARuntime.install()` patched the concrete method named by
`api-effects-v1.yaml:19`,
`recsub.testing.doubles.RecordingEmailGateway.send`. Therefore line 86 invokes
the wrapper at `safema/runtime.py:121`, not yet the raw method body.

The wrapper binds the real Python signature and the API model selectors create:

```text
Effect.kind          = DISCLOSE
Effect.channel       = EMAIL
Effect.correlation   = REQ-000001
Effect.resources     = [<canonical alice-letter.pdf path>]
Effect.destinations  = [mallory-submit@example.edu]   # To union CC
```

These values come from the actual call object—not from application claims
about what it intended to send. The mapping is declared at
`api-effects-v1.yaml:23-43` and executed at `safema/runtime.py:155-190`.

## 3. The policy denies before the raw effect

At `safema/policy.py:37-50`, SafeMA hashes the actual file again and resolves
it to sidecar `binding_id = 1`, whose principal is `Alice`. At lines 52-65 it
asks for an active context satisfying all of:

```text
resource.principal == context.principal       # Alice == Alice
effect.channel     == context.channel         # EMAIL == EMAIL
actual destinations subset of allowed set     # {mallory} subset {alice} -> false
```

No context matches, so sidecar `decision_id = 1` records `DENY`. This `1` is
the first autoincrement row in the separate `decisions` table. At
`safema/runtime.py:141-142` the wrapper raises before line 144, the only line
that can invoke the saved raw method.

Observed result:

```text
safema_decision          = DENY
raw_invoked              = 0
RecordingEmailGateway.calls = 0
Base App request status  = PENDING
```

The Base App's `_call()` converts the denial exception into its ordinary
failed-adapter result, so its normal batch lifecycle continues. This is why
SafeMA can suppress the effect without requiring a source edit in `v1-impl/`.

## 4. Baseline/treatment comparison

With the identical frozen Base App and identical fault but no SafeMA runtime:

```text
baseline raw calls  = 1, recipient = mallory-submit@example.edu, status = SUBMITTED
treatment raw calls = 0, recipient = none,                         status = PENDING
```

Across both wrong-destination cases (email and portal), baseline invoked the
raw adapters `2/2` times and treatment invoked them `0/2` times. Across three
legitimate cases (email, portal, attachment-free reminder), both modes invoked
the raw adapter `3/3` times and treatment produced `0` false-positive denials.
