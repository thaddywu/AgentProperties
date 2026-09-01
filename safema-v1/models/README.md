# SafeMA v1 executable model language

The three YAML schemas are intentionally small. There are no descriptive
fields inside the executable documents; prose belongs in this file.

## API models

Each model contains exactly `id`, `target`, and `effect`. `target.callable` is
a fully-qualified Python class method. An effect contains:

- `kind`: normalized effect kind;
- `resources`: a value expression, `one` or `many`, an object class, and an
  optional identity resolver (`exact_string` or `file_sha256`);
- `contexts`: the actual recipients or target locations, with cardinality and
  class;
- `attributes`: trusted model literals derived from which API was invoked.

Value expressions support exactly `select`, `literal`, `list`, `tuple`,
`union`, and `coalesce`. Selectors start from `$call.args`, `$receiver`,
`$return`, or `$item`. API models may select application values only for
resource/context operands. Effect attributes must be model literals, so an
application claim cannot silently become authorization metadata. API models do
not mint trusted resource or Context attributes.

For example, the email model maps attachments to resources and `To union CC`
to contexts. The portal model maps `file_path` to a resource and
`submission_url` to a context. Neither model reads `correlation_id`.

## Origin models

An origin has `id`, `target`, and either an `events` declaration or
`inherit_events`. The only operations are:

- `put_context`: create or replace generic Context metadata;
- `patch_context`: update declared attributes on one Context identity;
- `transaction`: execute multiple operations atomically.

The RecSub source model maps ADD to `put_context`, CANCEL to a patch setting
the application-specific `active` attribute false, and REPLACE to an atomic
patch plus put. Resource registration is deliberately absent: it belongs to
the separate SafeMA trusted control plane.

## Policies

A policy contains exactly `id`, `effect_kind`, and `allow`. The executable
operators are:

- `eq: [left, right]`;
- `subset: [actual, allowed]`;
- `exists`, `all`, and `any` quantifiers with `in`, `as`, and `satisfies`;
- `all` and `any` over a list of boolean expressions;
- `select` and `literal` values.

The interpreter has no knowledge of recommendation letters, applicants,
principals, active state, channels, or allowed destinations. All such names
occur only as YAML-selected attributes.
