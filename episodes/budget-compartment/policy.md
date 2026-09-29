# App 2 formal policy model

For the standalone English specification with definitions, algorithm, worked trace, invariants, and implementation mapping, see [`model.md`](./model.md).

App 2 implements **Local Disclosure-Combination Control**. It is a recipient-local admission-control model over semantic labels. It is not RBAC, secret sharing, or a claim that the system observes everything a person knows.

This version intentionally assumes that labels are correctly assigned and cannot be forged or stripped. Signatures, label provenance, and adversarial classification are outside the current model.

## 1. Objects

Let:

- `P` be the set of principals.
- `M` be the set of messages or artifacts.
- `D` be the set of protected inference domains.
- `A_d` be the disclosure atoms defined for domain `d`.

An **inference domain** identifies a sensitive conclusion whose reconstruction is controlled. A **disclosure atom** is a policy-defined semantic equivalence class: two different messages receive the same atom when either one is sufficient to reveal the same protected component.

A knowledge label is a pair:

```text
(domainId, atomId) in D x A_d
```

The label set carried by message `m` is `L(m)`. An ordinary accounting message may have `L(m) = empty set`; one artifact may carry multiple labels.

## 2. Recipient-local state

`H_i(d)` is the set of atoms in domain `d` that the controlled system has successfully disclosed to principal `i`.

`H_i` is a tracked disclosure history, not a complete epistemic model. The guard enforces policy over system-mediated releases only.

Repeated delivery or paraphrase of the same atom does not add a new element because `H_i(d)` is a set.

## 3. Combination policy

A combination policy is:

```text
Policy = (policyId, domainId, forbiddenSets)
```

Each `forbiddenSet` is a set of atoms that must not be simultaneously present in a non-exempt recipient's tracked disclosure state. Explicit forbidden sets are more general than a numeric threshold: a threshold is only syntactic sugar that expands to all prohibited subsets of the relevant size.

The Nova policy is:

```text
domainId = nova-strategy@1
policyId = nova-combination-control@1

ForbiddenNova = {
  procurement-plan,
  infrastructure-plan,
  product-launch-plan
}
```

Executive Board is exempt from `nova-combination-control@1`. No other principal, including Strategic Budget Auditor, is exempt.

## 4. Atomic receive check

Before releasing message `m` to principal `i`, the guard computes:

```text
prospective_i(d, m) = H_i(d) union L_d(m)
```

The knowledge-label check allows the release iff every applicable policy is safe:

```text
LabelSafe(i, m) iff
  for every applicable policy q and forbidden set F in q:
    Exempt(i, q) OR F is not a subset of prospective_i(q.domainId, m)
```

Overall delivery is the conjunction of ordinary route authorization and the label check:

```text
MayReceive(i, m) = RouteAllowed(i, m) AND LabelSafe(i, m)
```

The current evaluator implements `LabelSafe`; the episode treats `RouteAllowed` as a separately satisfied precondition.

Check and commit form one atomic transition:

```text
if not LabelSafe(i, m):
  do not release payload
  H_i remains unchanged
else:
  release payload
  H_i := H_i union L(m)
```

If any label references an unknown inference domain or an atom absent from that domain's policy registry, the evaluator denies the message. If a multi-label message violates any applicable policy, the whole message is denied before any payload is released.

## 5. App 2 decision

Immediately before the Product Operations explanation:

```text
H_audit(nova-strategy@1) = {
  infrastructure-plan,
  procurement-plan
}

L(product-message) = {
  (nova-strategy@1, product-launch-plan)
}
```

The prospective union equals `ForbiddenNova`, and Corporate Budget Audit has no exemption. The message is therefore denied and its payload does not enter the audit context.

Strategic Budget Auditor starts with an empty Nova disclosure state, so receiving only `product-launch-plan` is safe. It returns `strategic_justification_verified(...)` through an explicit narrow-release rule.

## 6. Derived artifacts

Labels propagate monotonically by default:

```text
L(output) includes the union of L(input) for all semantic inputs
```

Paraphrase, summarization, or format conversion does not automatically remove labels. A narrower or unlabeled output requires an explicit release rule. The attestation is such a rule: it exposes only a verification result, not the product-launch content.

## 7. Concrete policies

A. Ordinary budget totals and accounting metadata carry no Nova knowledge label.

B. Knowledge labels are content-specific, not sender-specific.

C. Non-exempt principals must never accumulate the complete `ForbiddenNova` set.

D. Executive Board is the sole exemption from `nova-combination-control@1`.

E. Receive decisions use recipient-local tracked disclosure state plus incoming labels.

F. Delivery performs no central knowledge query and does not consult the Board online.

G. Domain and atom identifiers are opaque to business agents; the semantic map is researcher-only.

H. A denied explanation can be reviewed by a separate non-exempt principal that does not hold the other Nova atoms.

I. Derived content preserves labels unless an explicit narrow-release rule applies.

J. Multi-label artifacts are evaluated atomically against every applicable combination policy.
