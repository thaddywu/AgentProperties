# Trust audit

## Decision inputs

| Value | Provenance | Role |
| --- | --- | --- |
| actual attachment or file path | EFFECT_OPERAND | normalized and hashed at the effect boundary |
| actual To, CC, or portal URL | EFFECT_OPERAND | normalized from the concrete call |
| file identity and attributes | TRUSTED_ATTRIBUTE | minted only by the SafeMA control plane |
| request-world Context attributes | TRUSTED_ATTRIBUTE | minted by a configured trusted source origin |
| API kind and constant channel | trusted deployment model | derived from which modeled API was invoked |
| correlation/request/letter IDs | UNTRUSTED_HINT | not present in the Effect and not policy-visible |
| Base App applicant or principal claims | UNTRUSTED_HINT | never mint trusted metadata |

## Trusted attribute origins

Resource identity and attributes are minted by the professor-facing SafeMA
control plane. The control plane reads the actual file, computes canonical path
and SHA-256, and stores the supplied administrative attributes. Base App letter
registration has no sidecar effect.

Destination authority attributes are minted from configured request-source
events. The deployment, not the Base App, selects those source implementations
and controls their backing world. SafeMA observes the return before the Base App
receives it and records event identity for idempotency.

The local prototype assumes the professor/harness and configured source world
are trusted. It does not provide cryptographic caller authentication, sidecar
file isolation, or protection against a hostile process that can mutate the
Python runtime or deployment YAML.
