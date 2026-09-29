# Local Disclosure-Combination Control

## Model specification for App 2

### Executive summary

App 2 controls combinations of disclosures rather than access to individual messages.

A message may be harmless on its own but unsafe when combined with information that the recipient has already received. Each policy-relevant message therefore carries one or more semantic **knowledge labels**. Before releasing the payload, the recipient's local guard combines the incoming labels with its tracked disclosure state and checks the result against explicit **forbidden sets**.

```text
tracked disclosure state
        +
incoming knowledge labels
        ↓
prospective disclosure state
        ↓
forbidden-set check
        ↓
     ALLOW / DENY
```

The model is called **Local Disclosure-Combination Control (LDCC)**.

It is:

- recipient-local;
- stateful;
- content-sensitive;
- based on semantic disclosure classes;
- independent of a central knowledge database.

It is not:

- ordinary role-based access control;
- a sender-to-recipient allowlist;
- secret sharing;
- a complete model of everything a human or agent knows.

This version assumes that labels are correct and cannot be forged, removed, or substituted. Signatures, label provenance, and adversarial labeling are intentionally outside the present model.

---

## 1. Motivation

Suppose Corporate Budget Audit is allowed to investigate three unusual budget increases:

1. a custom-accelerator purchase;
2. a large infrastructure expansion;
3. a new enterprise product launch.

Each explanation is individually appropriate audit material. However, receiving all three explanations would reveal the complete unannounced Project Nova strategy.

A route-level rule cannot express this distinction:

```text
Product Operations → Budget Audit is allowed
```

The route is valid. The individual message is valid. The unsafe condition exists only in the combination of the new disclosure and the recipient's prior disclosures.

LDCC therefore evaluates the recipient's **prospective disclosure state**, not just the message or route in isolation.

---

## 2. Vocabulary

### 2.1 Inference domain

An **inference domain** identifies a sensitive conclusion whose reconstruction is controlled.

```text
nova-strategy@1
```

The domain is not a folder, security clearance, or group of users. It is the namespace of one combination policy problem: reconstructing the Project Nova strategy.

The version suffix is part of the identifier. Changing the semantic definition of the domain should create a new version.

### 2.2 Disclosure atom

A **disclosure atom** is a policy-defined semantic equivalence class of information.

```text
procurement-plan
infrastructure-plan
product-launch-plan
```

An atom is not a sentence, file, or arbitrary document fragment. Two differently worded artifacts belong to the same atom when either artifact is sufficient to disclose the same policy-relevant component.

For example, all of the following may disclose `infrastructure-plan`:

- “Site West will add 35 MW by Q1.”
- a capacity chart showing the same expansion;
- a summary that clearly identifies the Site West buildout.

Repeated delivery or paraphrase of the same atom does not create a new atom.

### 2.3 Knowledge label

A **knowledge label** identifies the inference domain and disclosure atom revealed by an artifact.

```ts
interface KnowledgeLabel {
  domainId: string
  atomId: string
}
```

Example:

```json
{
  "domainId": "nova-strategy@1",
  "atomId": "infrastructure-plan"
}
```

A message carries a set of labels. It may carry no labels, one label, or labels from multiple domains.

### 2.4 Tracked disclosure state

For principal `i`, `H_i(d)` is the set of atoms in domain `d` that the controlled system has successfully disclosed to that principal.

```text
H_budget_audit(nova-strategy@1) = {
  infrastructure-plan,
  procurement-plan
}
```

This is a system-maintained disclosure history. It is deliberately not called “everything the principal knows.” The guard cannot observe information obtained outside the controlled disclosure path.

### 2.5 Forbidden set

A **forbidden set** is an explicit set of atoms that a non-exempt principal must not simultaneously accumulate.

```text
ForbiddenNova = {
  procurement-plan,
  infrastructure-plan,
  product-launch-plan
}
```

Forbidden sets are more precise than a numeric threshold. A threshold such as “no more than two atoms” is only correct when every three-atom combination is equally sensitive. Explicit sets can represent policies where only particular combinations are unsafe.

### 2.6 Policy exemption

A **policy exemption** permits a named principal to violate a particular combination policy.

```text
exempt(executive_board, nova-combination-control@1)
```

Exemptions apply to policy identifiers, not globally to every inference domain.

---

## 3. Formal model

Let:

- `P` be the set of principals;
- `M` be the set of messages or artifacts;
- `D` be the set of inference domains;
- `A_d` be the set of registered atoms for domain `d`;
- `L(m) ⊆ D × A_d` be the labels carried by message `m`;
- `H_i(d) ⊆ A_d` be principal `i`'s tracked disclosure state for domain `d`.

A combination policy is:

```text
q = (policyId, domainId, forbiddenSets)
```

where each member of `forbiddenSets` is a subset of `A_domainId`.

For an incoming message `m`, define the labels for domain `d` as:

```text
L_d(m) = { atom | (d, atom) ∈ L(m) }
```

The prospective state is:

```text
H'_i(d, m) = H_i(d) ∪ L_d(m)
```

The message is safe under policy `q` when the recipient is exempt or no forbidden set is fully contained in the prospective state:

```text
Safe_q(i, m) ⇔
  Exempt(i, q)
  ∨
  ∀F ∈ q.forbiddenSets : F ⊄ H'_i(q.domainId, m)
```

The complete knowledge-label decision is:

```text
LabelSafe(i, m) ⇔ ∀ applicable q : Safe_q(i, m)
```

Normal communication authorization remains a separate conjunct:

```text
MayReceive(i, m) ⇔ RouteAllowed(i, m) ∧ LabelSafe(i, m)
```

The current evaluator implements `LabelSafe`. The episode treats `RouteAllowed` as an already-satisfied precondition.

---

## 4. State transition

The receive check and state update must be one atomic operation.

```text
receive(i, message):
  incoming    := Labels(message)
  prospective := DisclosureState(i) ∪ incoming

  if incoming references an unknown domain or atom:
    return DENY

  for each policy affected by incoming:
    if i is not exempt from policy:
      if prospective contains any policy.forbiddenSet:
        return DENY

  release message payload to i
  DisclosureState(i) := prospective
  return ALLOW
```

Atomicity matters. Without it, two simultaneous messages could both read the same old state, independently pass, and collectively create a forbidden state.

### Denial semantics

When the result is `DENY`:

- the payload is not released into the recipient's context;
- the recipient's disclosure state does not change;
- simulator instrumentation may still display the withheld payload to the researcher;
- the business workflow may take an alternative path.

### Multi-label messages

The guard evaluates every affected policy before releasing any part of the payload. If one policy fails, the entire message is denied.

There is no partial release unless the application explicitly divides the artifact into independently releasable messages.

---

## 5. Project Nova policy

The App 2 registry contains the following policy:

```ts
const novaPolicy = {
  id: 'nova-combination-control@1',
  domainId: 'nova-strategy@1',
  forbiddenSets: [[
    'procurement-plan',
    'infrastructure-plan',
    'product-launch-plan',
  ]],
}
```

Only Executive Board has the corresponding exemption:

```text
policyExemptions(executive_board) = {
  nova-combination-control@1
}
```

Strategic Budget Auditor has no exemption. Its review is safe because it receives only one Nova atom, not because its role bypasses the policy.

---

## 6. Worked receive trace

Immediately before the Product Operations explanation, Budget Audit has:

```text
Current state:
{
  infrastructure-plan,
  procurement-plan
}
```

The incoming message carries:

```text
Incoming labels:
{
  product-launch-plan
}
```

The guard computes:

```text
Prospective state:
{
  infrastructure-plan,
  procurement-plan,
  product-launch-plan
}
```

Decision table:

| Check | Result |
|---|---|
| Domain is registered | Yes |
| Atom is registered | Yes |
| Route is allowed | Yes |
| Recipient has policy exemption | No |
| Prospective state contains `ForbiddenNova` | Yes |
| Final decision | **DENY** |

The message is individually legitimate and the sender-recipient route is legitimate. The denial is caused only by the recipient-specific combination.

Budget Audit's state remains:

```text
{
  infrastructure-plan,
  procurement-plan
}
```

---

## 7. Independent review and narrow release

After denial, Product Operations sends the `product-launch-plan` explanation to Strategic Budget Auditor.

The reviewer starts with an empty Nova state:

```text
∅ ∪ { product-launch-plan }
  = { product-launch-plan }
```

This does not contain `ForbiddenNova`, so the receive is allowed.

The reviewer then returns:

```text
strategic_justification_verified(
  q1_q2_budget_package,
  approved
)
```

This attestation is not an ordinary summary of the protected explanation. It is the output of an explicit **narrow-release rule** that reveals only a verification result.

---

## 8. Derived artifacts

Labels are monotonic by default.

If output `y` is derived from inputs `x₁ ... xₙ`, then:

```text
L(y) ⊇ L(x₁) ∪ ... ∪ L(xₙ)
```

Therefore the following operations do not automatically remove labels:

- paraphrasing;
- summarization;
- translation;
- format conversion;
- extracting a passage that still reveals the same atom.

A label may be removed or replaced only by an explicitly defined release rule whose output semantics are narrower than its inputs.

The current episode models one such rule:

```text
input:
  product-launch-plan

output:
  strategic_justification_verified(...)

output labels:
  ∅
```

The correctness of that release rule is assumed by this version of the model.

---

## 9. Required invariants

For every non-exempt principal `i` and policy `q`:

```text
∀F ∈ q.forbiddenSets : F ⊄ H_i(q.domainId)
```

The implementation should preserve the following operational invariants:

1. **Pre-release checking** — the payload is checked before entering recipient context.
2. **Atomic check and commit** — no concurrent receive can bypass the prospective-state test.
3. **Set semantics** — duplicate labels do not increase disclosure state.
4. **Fail-closed registry lookup** — unknown domains and atoms are denied.
5. **Whole-message decision** — a multi-label message is released only if every applicable policy passes.
6. **Denial is non-mutating** — denied labels are not added to recipient state.
7. **Policy-scoped exemption** — an exemption applies only to its named policy.
8. **Label-preserving derivation** — derived content keeps input labels unless an explicit release rule applies.

---

## 10. What the model can and cannot claim

LDCC can claim:

- the controlled system did not release a forbidden label combination to a non-exempt recipient;
- each decision used only recipient-local state, incoming labels, and local policy configuration;
- the Board was not consulted as an online oracle;
- individually valid messages can receive different decisions for different recipients.

LDCC cannot by itself claim:

- that the recipient learned nothing equivalent from an uncontrolled source;
- that labels were assigned correctly;
- that a sender could not remove or forge a label;
- that the narrow-release rule is semantically sound;
- that labels remain trustworthy across organizational boundaries.

Those questions require additional classifier, provenance, signature, and declassification models. They are intentionally deferred.

---

## 11. Implementation mapping

| Model concept | Implementation |
|---|---|
| Knowledge label | `KnowledgeLabel { domainId, atomId }` |
| Tracked disclosure state | `LocalView.disclosureState` |
| Policy exemption | `LocalView.policyExemptions` |
| Combination policy | `CombinationPolicy` |
| Forbidden-set evaluator | `evaluateDisclosureReceive(...)` |
| Incoming labels | `Message.knowledgeLabels` |
| Decision evidence | `EpisodeStep.disclosureDecision` |
| Semantic instrumentation | `ResearcherViewConfig.domains` |

The pure evaluator is implemented in `src/policy/disclosure.ts`. The episode frames remain declarative snapshots for deterministic replay; a production runtime would place the evaluator and disclosure-state update inside one transactional receive operation.

---

## 12. Short form

The entire model can be summarized as:

```text
Messages carry semantic disclosure labels.

Each recipient tracks the labels previously released to it.

Before releasing a new payload, the local guard unions the old and incoming labels.

If that prospective state contains an explicit forbidden set, and the recipient has no exemption for that policy, the payload is denied and state is unchanged.
```
