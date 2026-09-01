# SafeMA focused core prototype

SafeMA intercepts modeled effectful APIs, maps their actual operands into a
small security-effect representation, resolves security attributes from
independently trusted origins, and evaluates executable declarative policies
before the raw effect. The frozen Base App in `v1-impl/` is unchanged.

## Trust boundary

The Base App and every identifier or claim it supplies are untrusted for
authorization. In particular, `Application.register_letter(...)`, request IDs,
letter IDs, and correlation IDs cannot mint SafeMA metadata.

Two explicitly trusted administrative inputs exist in this local prototype:

1. `TrustedControlPlane.register_resource(...)`, invoked by the professor or
   experiment harness outside the Base App. It computes file identity itself
   as canonical path plus SHA-256 and writes resource attributes to the SafeMA
   sidecar.
2. Request-source adapters listed in `trusted-origins-v1.yaml`. Deployment is
   assumed to control those adapters and their backing world. Their returned
   ADD/CANCEL/REPLACE events mint or update trusted Context metadata.

This prototype does not cryptographically authenticate the administrative
caller and does not isolate the sidecar with OS capabilities. Those are stated
deployment assumptions, not properties of Python monkey-patching.

## Three separate executable models

- `models/api-effects-v1.yaml` says which concrete method to intercept and how
  its actual arguments become Effect resources, contexts, and attributes.
- `models/trusted-origins-v1.yaml` says which configured source methods can
  mint Context metadata and how their lifecycle events update it.
- `policies/recommendation-disclosure-v1.yaml` contains the complete
  recommendation-disclosure authorization expression.

Every YAML field is strictly validated. Unknown fields, unsupported operators,
unsupported identity resolvers, and modeled effect kinds without a policy fail
during runtime startup.

## Generic IR

```text
Resource { identity, class, attributes }
Context  { identity, class, attributes }
Effect   { kind, resources, contexts, attributes }
```

`applicant`, `purpose`, `active`, `channel`, and `allowed_destinations` are
RecSub policy attributes, not SafeMA core fields. Correlation is absent from
the security Effect.

## Local workflow

Install the package, then use one persistent sidecar path for every command:

```bash
python -m pip install -e ./safema-v1

safema-recsub --metadata-db ./safema.sqlite3 -- \
  --config ./config.json sync

safema-recsub --metadata-db ./safema.sqlite3 -- \
  --config ./config.json register-letter \
  --path ./alice.pdf --applicant Alice --purpose PHD_APPLICATION

safema-register-resource --metadata-db ./safema.sqlite3 \
  --path ./alice.pdf --resource-class recommendation_letter \
  --attributes-json '{"applicant":"Alice","purpose":"PHD_APPLICATION"}'

safema-recsub --metadata-db ./safema.sqlite3 -- \
  --config ./config.json process
```

The Base App registration is still needed for its matching workflow, but it
does not authorize disclosure. Only the separate SafeMA control-plane command
mints the trusted resource attributes.

## Verification

```bash
PYTHONPATH=safema-v1:v1-impl python -m pytest -q safema-v1/tests
PYTHONPATH=safema-v1:v1-impl python safema-v1/evaluation/run_v1.py
```
