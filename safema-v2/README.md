# SafeMA v2 shared runtime

SafeMA v2 preserves the model-driven effect interception and trusted metadata
core used by SafeMA v1 while adding the minimal generic capabilities required
by the multi-supplier replenishment case study:

- deployment-registered receiver-instance bindings;
- live trusted-state resolvers invoked immediately before policy evaluation;
- dynamic actual-call operands in normalized Effect attributes;
- exact integer/Decimal `add`, `mul`, `mod`, `gt`, `gte`, `lt`, and `lte`
  operators; and
- an optional integration-level denial handler for APIs whose protocol uses a
  definitive no-effect result rather than an exception.

The runtime remains application-agnostic. It has no built-in concept of SKUs,
inventory, suppliers, recommendation letters, or purchasing limits. App-owned
integration code supplies trusted resolver implementations and denial-result
translation.

SafeMA v1 remains unchanged for the completed Recommendation Submission case.
