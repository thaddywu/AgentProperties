# Deep Scenario Search for SafeMA

Status: design and research only. No application or SafeMA implementation was added.

Last reviewed: 2026-09-02

## Scope, method, and evidence standard

This document preserves the design history of a sequential search for a second compelling SafeMA application. It records candidate policies, counterexamples, revisions, rejections, and the lessons that changed the next search. “Reasoning” here means reviewable design rationale and adversarial analysis, not an assertion that every speculative thought is evidence.

The target shape is:

```text
downstream service, using its own legitimate authority model: ALLOW
application-level policy, using independently trusted context: DENY
```

The downstream service must be correct on its own terms. SafeMA must inspect the actual operands at the consequential boundary and use trusted facts that the buggy Base App cannot simply invent. A candidate loses heavily if a well-engineered downstream service, ordinary vertical application module, transaction manager, workflow engine, or established security gateway is the obvious owner of the whole invariant.

The recommendation-letter application is the baseline. Its policy binds an artifact's semantic identity and provenance to an applicant-specific request, destination, purpose, and lifecycle. A new case should not merely rename that relation, and should not be an approved plan that became stale before execution.

Research is grounded primarily in current official product documentation and public standards. The sources establish that workflows and controls exist; they do not establish that SafeMA is uniquely necessary.

## Inherited rejection history

The prior HotCRP exploration is retained as design history:

- Reviewer conflicts, visibility, roles, decisions, and conference phases are naturally HotCRP-owned semantics. Adding SafeMA would duplicate downstream access control or business logic.
- An approved assignment or decision batch executed after state changes is stale authorization again.
- Posting a P17-derived summary into P18 is a real gap, but it is recommendation-style provenance-to-context binding.
- Preventing prose from semantically leaking blind-review facts needs information-flow tracking and semantic classification, with poor precision if implemented conservatively.
- A reviewer/final-decision separation-of-duty rule was rejected because it was manufactured rather than grounded in conference practice.

This starting history immediately creates five rejection classes: downstream owns the semantics; stale authorization redux; provenance-to-destination duplication; semantic IFC; and ungrounded policy.

## Initial working hypothesis

The first hypothesis was that strong applications would combine a generic powerful effect API, structured evidence distributed across systems, a compact predicate, and an irreversible or expensive effect. The search below revises this hypothesis: distributed evidence is helpful, but it is not enough if a familiar upstream application module naturally owns the join.

# Application Exploration 1: Cross-system accounts-payable payment

## Stage A: Real application

Accounts payable normally receives a supplier invoice, matches it to a purchase order and receipt, resolves variances, approves/posts it, and selects an installment for payment. Microsoft defines three-way matching as comparing invoice price with the purchase order and invoice quantity with selected product receipts. Oracle documents automatic matching holds when billed amount or quantity exceeds ordered or received amount, and states that holds prevent payment. Integrated products also provide payment-process requests that select validated installments. [Microsoft invoice matching](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching), [Oracle hold types](https://docs.oracle.com/en/cloud/saas/financials/26a/fappp/types-of-holds.html), [Oracle payment process requests](https://docs.oracle.com/en/cloud/saas/financials/26c/fappp/payment-process-requests.html)

Principals are buyer/procurement staff, receiving staff, AP staff or agent, supplier, approver, and payment-rail operator. Resources are PO lines, receipt and reversal events, invoice lines, vendor bank identities, installments, and transfers. Consequential operations are invoice approval/posting, hold release, and the actual transfer.

In an integrated ERP, the ERP owns the PO, receipt selection, invoice, tolerance, hold, and payment-release state. In a split deployment, procurement, a warehouse system, invoice intake, and a generic payout API may be separate. A payment API can legitimately accept an authorized destination and amount without knowing why the payer believes the money is owed. Wise, for example, exposes a transfer workflow with a target account and amount; that is money movement, not invoice adjudication. [Wise transfer API](https://docs.wise.com/guides/product/send-money/standard-api-transfers)

## Stage B: Candidate semantic gaps

1. The payment rail knows credentials, destination validity, funds, and rail rules, but not received quantity.
2. Procurement knows ordered quantity and price but not physical receipt reversals or prior payouts.
3. Receiving knows received quantity but not invoice identity, vendor bank mapping, or payment consumption.
4. A duplicate or overlarge transfer may fit bank-level limits while exceeding the current business obligation.

These are genuine cross-service gaps, but the crucial responsibility question is whether an AP matcher is already the natural owner.

## Stage C: Policy v0 — pay approved invoices

```text
ALLOW PAY(payee, currency, amount, invoice_ref)
IFF invoice_ref has status APPROVED and the operands equal the approval.
```

Normal trace: `INV-884` for $7,200 is approved; the agent calls `PAY(V.account, USD, 7200, INV-884)`; SafeMA allows and consumes the approval.

Violating trace: the same approval exists, but the agent calls $12,000; the payout API accepts the authorized company's request; SafeMA denies the operand mismatch.

## Stage D: First adversarial critique

The strongest rejection is: this is an approval token in AP clothing. If the approval is exact, it is close to prior approved-plan examples; if it can become invalid after a receipt reversal or vendor-account change, it is stale authorization. The status is also dangerous if the Base App can set `APPROVED` itself. An ERP should already prevent held or unvalidated invoices from entering its payment process, and Oracle explicitly does so. SafeMA v0 contributes no distinctive application structure.

The complete attack is unfavorable:

- It is not bank access control, but it is ordinary invoice workflow authorization.
- The bank should not enforce it; the AP system should.
- A Base App check is insufficient for fault independence, but duplicating the same status check is a very small research contribution.
- The trusted origin for approval is underspecified.
- Exact approval introduces one-use state but otherwise repeats known examples.

Policy v0 is rejected.

## Stage E: Revision v1 — recompute a live bounded obligation

Change the Base App from “an ERP with an agent UI” to an integration agent spanning independently administered procurement, warehouse, invoice intake, and a generic payment rail. Remove `APPROVED` from the decision. SafeMA ingests immutable PO/amendment events, warehouse receipt/reversal events, authenticated invoices, vendor-to-bank mappings, and its own successful-payment events.

For a deliberately simplified first case with no tax, tolerances, credits, or manual overrides:

```text
ALLOW PAY(payee, currency, amount, invoice_ref)
IFF there is exactly one unpaid trusted invoice I with invoice_ref
AND payee = trusted_bank_account(I.vendor)
AND currency = I.currency = I.PO.currency
AND I.PO is open and names I.vendor
AND for every invoice line l:
      l.unit_price = PO[l.po_line].unit_price
      paid_qty[l.po_line] + l.qty <= received_not_reversed_qty[l.po_line]
AND amount = SUM(l.qty * l.unit_price)
AND invoice_ref has not been consumed.
```

On definitive transfer success, SafeMA atomically records the invoice as paid and consumes the applicable quantities. A reservation is needed before the call if concurrent agents can pay.

Normal trace: PO-41 orders 100 drives at $120. Sixty are received, and INV-884 bills 60. No earlier payment exists. The actual call is `PAY(V.account, USD, 7200, INV-884)` and is allowed.

Violating trace: the invoice bills all 100 drives for $12,000 even though the trusted warehouse has recorded only 60. The agent confuses ordered with received quantity and calls `PAY(V.account, USD, 12000, INV-884)`. The payment rail reasonably allows the authorized transfer. SafeMA computes a maximum matched quantity of 60 and denies.

## Stage F: Second adversarial critique

This is more distinct: a relational join, numeric upper bound, aggregation, and consumption history rather than exact approval or artifact routing. It remains exposed to a devastating systems/domain objection: invoice matching is precisely what AP software does. Microsoft and Oracle do not merely store these facts; they implement matching, discrepancy handling, holds, workflow, and payment selection. Splitting the products does not magically make the join cease to be AP logic.

The direct-agent-to-bank design is realistic for some integration-heavy or smaller organizations, but a skeptical engineer can say, “Put a narrow AP service between the agent and the bank; that service is the matcher.” If that service is only a compact reference monitor it begins to resemble SafeMA, but calling ordinary AP validation “SafeMA” risks relabeling a domain module.

Trust is also nontrivial. Invoice authenticity, vendor bank changes, receipt reversals, partial invoices, tolerances, taxes, credits, duplicate invoice numbers, concurrency, and payment failures all matter in production. The simplified predicate is locally mockable, but its claim must remain narrow.

## Stage G: Revision v2 — independent payment authority, then another attack

A trusted matching service could issue a one-use bounded authority:

```text
payment_capability = {
  invoice_ref, payee, currency, max_amount, expiry, remaining_amount
}
```

SafeMA would enforce that the actual transfer is no broader than the capability and consume it after success. This cleanly separates rich AP logic from a small effect guard.

That revision improves implementability but weakens distinctiveness: it is capability attenuation plus one-use consumption, and the matcher still must exist. SafeMA is useful as the last-mile consumer of the capability, but the application family no longer demonstrates SafeMA discovering a rich invariant on its own.

## Three-reviewer test

- **Security reviewer:** v1 is a reference monitor over a quantitative capability; v2 makes that explicit. There is no new primitive beyond structured authority and consumption.
- **Systems reviewer:** a dedicated AP/matching service naturally owns the invariant. SafeMA is defensible as an independent last-mile kernel, not as the only plausible architecture.
- **Domain engineer:** integrated ERP deployments already place and honor matching holds. Only genuinely disjoint systems with direct payout credentials fit.

## Final verdict

**PROMISING BUT UNRESOLVED**

The policy is consequential, crisp, and importantly different from recommendation routing. The unresolved issue is not technical feasibility; it is architectural ownership. This family survives only if the intended contribution is an independent, generic effect guard even when a domain matcher also exists.

## Lesson for the next search

Cross-system joins create a semantic gap, but a gap is not enough. Search next for a destructive effect whose downstream system cannot see the required witness and for which the natural safety mechanism is itself a narrow interlock rather than a full vertical application module.

# Application Exploration 2: Cross-provider recovery before destructive decommissioning

## Stage A: Real application

The application is a decommissioning assistant, not a general backup product. It retires an old storage/database account after migration to another provider or separately administered account. It transfers an immutable recovery point, validates it, establishes retention, then removes the final source-side recovery point and eventually the source account.

Principals are the service owner, migration operator or agent, source administrator, destination backup administrator, and independent recovery verifier. Resources are an immutable source snapshot, transfer manifest, destination recovery point, encryption dependencies, retention configuration, restore-test result, and source deletion operation.

Real controls distinguish several facts:

- AWS DataSync always checks during transfer and can additionally compare checksums for transferred data or the entire source/destination. “Transfer complete” and end-of-transfer verification are therefore distinct. [AWS DataSync verification](https://docs.aws.amazon.com/datasync/latest/userguide/configure-data-verification-options.html)
- AWS Backup restore testing performs actual restore jobs, and an optional validation workflow can test the restored resource and report `SUCCESSFUL`. [AWS restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html), [restore validation](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing-validation.html)
- AWS supports cross-account backup copies and recommends separate accounts for restore tests; Vault Lock can make retained recovery points immutable. [Cross-account copies](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-cross-account-backup.html), [Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- Native source protections exist. RDS deletion protection blocks deletion, and RDS can take a final snapshot or retain automated backups. These must not be ignored when claiming a gap. [RDS deletion](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)

Consequential effects include deleting a database instance, snapshot, object version, backup vault, or source account. The narrow case uses deletion of the last source-side recovery point after a cross-provider move.

## Stage B: Candidate semantic gaps

1. The source service knows whether the caller may delete and whether a local final snapshot exists, but not whether a separate provider/account holds a usable copy.
2. The destination knows a recovery point exists, but not which exact immutable source version is about to be destroyed.
3. A transfer service knows byte/metadata comparison, but not whether required keys, roles, and restore procedures actually work.
4. A restore validator knows a test succeeded, but does not control the later source deletion.

Unlike AP, no single downstream service naturally owns all these facts across provider and administrative boundaries.

## Stage C: Policy v0 — copy completion before delete

```text
ALLOW DELETE_SOURCE(snapshot_id)
IFF copy_job(snapshot_id).status = COMPLETED.
```

Normal trace: copy job C-9 completes, then the agent deletes S-37.

Violating trace: C-9 failed but the agent mistakes a terminal state for success; SafeMA denies.

## Stage D: First adversarial critique

This is too weak and potentially misleading. A completed job may have skipped objects, copied a mutable view, lost metadata, used an unavailable encryption key, or produced a recovery point that cannot restore. Job IDs supplied by the Base App are untrusted joins. A native migration orchestrator is supposed to sequence copy then cleanup, and source-native final snapshots/deletion protection may be safer. A reviewer can dismiss v0 in one sentence: “Use the transfer job's success flag and the platform's final-snapshot option.”

Policy v0 is rejected.

## Stage E: Revision v1 — exact-version verified replica

Bind the actual destructive operand to immutable source identity and independently produced evidence:

```text
ALLOW DESTROY_SOURCE(source, dataset, version, digest)
IFF EXISTS replica R:
    R.source = (source, dataset, version, digest)
    AND R.state = AVAILABLE
    AND R.digest = digest
    AND R.full_manifest_verification = SUCCEEDED.
```

The SafeMA adapter resolves the actual source version and digest. It does not trust an application-provided `copy_job_id` or `verified=true`.

Normal trace: source `lab/raw@v37` has digest D37; a destination recovery point is available and a trusted full-manifest verifier binds it to v37/D37; delete v37 is allowed.

Violating trace: the agent calls delete on v38 while presenting evidence for v37, or the v37 verification reports a missing shard. Source IAM legitimately permits either deletion; SafeMA denies because no matching witness exists.

## Stage F: Second adversarial critique

Checksum equality is necessary for byte integrity but does not prove recoverability. AWS explicitly separates restore testing from backup completion, and its validation hook exists because “restore job completed” need not mean “application works.” The destination copy might be in the same failure domain, have insufficient retention, depend on a soon-to-be-deleted key, or have been revoked after certification.

Conversely, requiring a fresh full restore test for every object version is unrealistic and costly. We were conflating file migration, database recovery, backup policy, and disaster recovery. The scenario needs a coarser protected unit and the smallest realistic witness.

## Stage G: Revision v2 — recovery certificate for one decommissioned dataset

Narrow the application to retiring one immutable database/dataset snapshot after a cross-provider or separately administered-account migration. A trusted recovery authority issues a certificate only after it has restored that exact recovery point into a disposable environment and run a small deterministic validation (for example, manifest count plus a database canary query). The destination must enforce a minimum retention window and be outside the source administrative/failure domain.

```text
ALLOW DESTROY_LAST_SOURCE_COPY(source_dataset_id, source_version, source_digest)
IFF EXISTS current recovery certificate C:
    C.source = (source_dataset_id, source_version, source_digest)
    AND C.destination_recovery_point is AVAILABLE
    AND C.restore_validation = SUCCEEDED
    AND C.destination_failure_domain != source.failure_domain
    AND C.retained_until >= now + required_rollback_window
    AND C.revoked = false.
```

The certificate is not a Base App assertion. It is minted by a configured recovery authority from destination-provider events and a validator run. It names the exact source snapshot/digest and destination recovery point. For an immutable source snapshot, later source mutation is eliminated. Revocation and destination deletion events invalidate the certificate.

Normal trace: snapshot v37/D37 is copied to archive account B, restore-tested, validated, and locked through October 31. The agent deletes the final source recovery point on September 2; SafeMA allows.

Violating trace: the transfer is marked complete, but restore validation failed because the encryption key was not available. The agent nevertheless calls the source provider's valid delete API. The source correctly sees an authorized admin and a deletable snapshot and allows. SafeMA sees no current certificate and denies.

## Stage H: Final attack and boundary audit

**Why not ordinary access control?** Source IAM can say who may delete and require a waiting period. It cannot condition deletion on a recovery point in another provider/account without importing foreign application semantics.

**Why not the downstream source service?** Source-native deletion protection and final snapshots are preferable while remaining in that service. The refined case begins where those controls end: decommissioning the source administrative domain itself after independently validated recovery elsewhere.

**Why not just the Base App?** The Base App performs the migration and is exactly the component that may confuse job states, versions, or validation results. The safety property is small enough to check independently at deletion.

**Is SafeMA duplicating an orchestrator?** Partly. A good orchestrator should check the same evidence. The distinction is that SafeMA does not schedule transfers, retries, cutover, or cleanup; it is a deny-only invariant shared by any agent/caller that reaches the destructive adapters. In a non-agentic design, a narrow deletion interlock or policy gateway is a natural owner—precisely the SafeMA-shaped boundary.

**Staleness and races:** a certificate cannot guarantee that the destination will never fail one nanosecond later. The defensible guarantee is conditional on current trusted availability/retention records and revocation delivery. Retention lock prevents ordinary deletion during the rollback window. The local experiment must not claim a distributed atomic guarantee against simultaneous catastrophic failure.

**Smallest realistic invariant:** exact snapshot identity + successful restore validation + independently enforced retention in a distinct administrative domain. Full-manifest verification may be evidence used to mint the certificate, but need not appear as a separate policy conjunct if the recovery authority's contract already includes it. Freshness is unnecessary for one immutable decommission snapshot if availability and retention revocations are monitored.

## Three-reviewer test

- **Security reviewer:** this is evidence-gated destruction, not IFC or ordinary principal/resource ACLs. A certificate is capability-like, but its meaning is cross-service recoverability.
- **Systems reviewer:** a backup orchestrator is an alternative, yet a reusable deny-only last-copy interlock across multiple destructive APIs remains a coherent separate component.
- **Domain engineer:** native final snapshots and deletion protection must be used when sufficient. Cross-account/provider decommission plus actual restore validation is recognizable operational practice, not an invented rule.

## Final verdict

**SURVIVES**

The refined application meets the semantic-gap standard and has a different policy shape: a destructive resource may cease to exist only when a durable recovery witness for that exact version exists elsewhere. The strongest remaining objection is that “recovery certificate” could become a renamed backup-orchestrator approval unless its origin contract and narrow deny-only role are explicit.

## Lesson for the next search

Destruction cases become strong when the downstream service sees only the thing being destroyed while independent systems see the preservation witness. Search next for another irreversible effect with a cross-system blast radius, but test whether the required evidence can ever be complete.

# Application Exploration 3: Cryptographic-key destruction and crypto-erasure

## Stage A: Real application

Key-management systems let authorized administrators disable or schedule destruction of key versions. Destruction is intentionally dangerous: AWS says deleting a symmetric KMS key makes remaining ciphertext unrecoverable and cannot be reversed; Google Cloud similarly warns of permanent data loss and service outage. Both use a waiting period, and both recommend disabling first when uncertain. [AWS key deletion](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html), [Google Cloud destroy/restore](https://docs.cloud.google.com/kms/docs/destroy-restore)

NIST defines cryptographic erase as sanitizing encryption keys so recovery of decrypted target data becomes infeasible. It is therefore also a legitimate deletion mechanism, not only an accident risk. [NIST cryptographic erase](https://csrc.nist.gov/glossary/term/cryptographic_erase)

The Base App is a key-lifecycle/offboarding agent. Principals are tenant owner, privacy/records authority, key administrator, storage owners, and the KMS. Resources are key versions, encrypted objects/data keys, tenant/deletion cohorts, holds and retention obligations, usage inventory, and the schedule-destruction call. The consequential boundary is scheduling destruction because it automatically progresses to irreversible destruction unless canceled.

## Stage B: Candidate semantic gaps

1. KMS knows key identity, state, IAM, and waiting-period policy but not which business objects depend on it.
2. Storage systems know their objects and encryption headers but not every other system sharing the key.
3. A privacy-deletion authority knows which tenant or subject should be erased but not the key's full collateral blast radius.
4. A key can be unsafe to destroy for either of two opposite reasons: protected data still needs recovery, or the intended crypto-erasure would be incomplete because another usable key/copy remains.

## Stage C: Policy v0 — no recent use

```text
ALLOW SCHEDULE_KEY_DESTRUCTION(key_version)
IFF no decrypt event for key_version occurred in the last 30 days.
```

Normal trace: a retired key has no recent uses; destruction is scheduled.

Violating trace: yesterday's decrypt shows active dependency; SafeMA denies.

## Stage D: First adversarial critique

Absence of recent use is not absence of dependency. A quarterly job, cold backup, or dormant ciphertext may still need the key. Google warns that usage tracking can be delayed or incomplete, excludes application use inside or outside Google Cloud, omits some resource types, and is informational only. [Google key-usage limitations](https://docs.cloud.google.com/kms/docs/view-key-usage)

This policy converts incomplete telemetry into a catastrophic negative claim. The waiting period and alerting are valuable native controls, but SafeMA cannot manufacture completeness. Policy v0 is rejected.

## Stage E: Revision v1 — all tracked resources re-encrypted

```text
ALLOW SCHEDULE_KEY_DESTRUCTION(K_old)
IFF inventory(K_old) is complete for declared scope S
AND every live resource in S formerly protected by K_old
    has a verified decrypt/rewrap/read under K_new
AND K_old has been disabled for a workload-specific observation interval
AND no failed dependency probe occurred.
```

This changes the proof from “no use observed” to positive migration evidence for a closed registered set, plus a disable-and-observe phase.

Normal trace: all 1,024 registered objects were rewrapped, sampled/read checks pass, the key has been disabled through a full monthly workload cycle, and no probes fail.

Violating trace: one registered cold archive remains bound to K_old; KMS IAM would permit scheduling deletion, while SafeMA denies the incomplete set.

## Stage F: Second adversarial critique

The phrase “inventory is complete” carries almost the entire guarantee. If applications can create ciphertext outside the registry or download an asymmetric public key, positive enumeration is incomplete. AWS explicitly notes that users may continue encrypting with an exported public key even after deletion is scheduled. A universal negative across arbitrary ciphertext is not locally enforceable without controlling all encryption paths.

The revision also looks like an ordinary key-migration runbook plus a safety gate. That is not fatal, but it is very close to the recovery-before-destruction family and adds a harder evidence problem.

## Stage G: Revision v2 — bounded crypto-erasure cohort

Try the opposite workflow: a multi-tenant SaaS uses a dedicated envelope-encryption key per tenant. A deletion authority requests crypto-erasure of tenant T. SafeMA has a trusted tenancy/key registry and independently scanned object manifests.

```text
ALLOW SCHEDULE_KEY_DESTRUCTION(K)
IFF deletion_authority.status(T) = ACTIVE
AND key_registry.dedicated_tenant(K) = T
AND every registered object/data-key wrapped by K belongs to T's deletion cohort
AND no such object is under retention or legal hold
AND no live replica is registered under a different recoverable wrapping key
AND requested waiting_period >= policy.minimum.
```

Normal trace: K-73 is dedicated to departed tenant T-73, all K-73 objects are eligible for deletion, and none is held; schedule destruction is allowed.

Violating trace: K-73 also wraps a shared billing archive or a held record. KMS sees an authorized key administrator and correctly allows scheduling. SafeMA sees collateral data outside the deletion cohort and denies.

## Stage H: Final attack

Dedicated per-tenant keys make the blast radius structured, but they also make much of the rule reducible to trusted key tags plus a tenant deletion authorization—capability/binding territory. Allowing shared keys makes the case interesting but makes inventory completeness dubious. Legal holds introduce records-management semantics that will be explored separately. The KMS waiting period means SafeMA could also cancel after detecting errors, reducing the need for synchronous denial, though preventing an erroneous schedule still matters because the key becomes unusable while pending deletion.

The strongest formulation is a closed-world deployment where SafeMA also mediates all data-key wrapping and maintains the key-to-object relation. That would provide trustworthy completeness, but it expands the enforcement boundary substantially and begins a key-governance system rather than a modest SafeMA extension.

## Three-reviewer test

- **Security reviewer:** crypto-erasure and key lifecycle are classical key-management governance; the distinctive part is set containment over collateral data.
- **Systems reviewer:** the complete key inventory and migration controller are the real system. A call interceptor alone cannot supply the guarantee.
- **Domain engineer:** disabling, observing, and using provider inventory are real practice, but providers warn that the inventory cannot prove non-use.

## Final verdict

**PROMISING BUT UNRESOLVED**

The downstream ALLOW/application DENY gap is excellent and the consequence is obvious, but a defensible policy needs a closed, trusted key-usage universe. Without that, SafeMA would lend false confidence to an irreversible action.

## Lesson for the next search

Universal negative claims (“nothing still depends on this”) are much harder than positive witnesses (“this exact recoverable copy exists”). Prefer candidates where trusted evidence is positively enumerable, and reject cases where native admission already provides the same complete boundary.

## Checkpoint comparison after three families

The recovery case is easier to explain than payment or key destruction in three sentences: an authorized agent tries to delete the last source copy; the source provider correctly allows its administrator; an independent restore-tested copy does not exist, so SafeMA denies. Its policy is also clearly different from recommendation routing and stale approval.

Payment has the crispest arithmetic but the weakest ownership story. Key destruction has the clearest consequence but the hardest evidence-completeness problem. Recovery currently sets the bar for the remaining search.

# Application Exploration 4: Attested CI/CD deployment

## Stage A: Real application

A release agent selects a container digest after build, tests, vulnerability scanning, signatures, and provenance attestations, then updates a Kubernetes workload. Principals are developer, CI builder, security scanner, release agent, registry, and cluster administrator. Resources are source revision, build run, image digest, attestations, deployment, and namespace policy. The consequential operation is Kubernetes admission/update.

This domain already has a purpose-built effect boundary. Sigstore's policy-controller is a Kubernetes admission controller that validates image signatures and attestations and resolves tags to digests; GitHub documents enforcing its artifact attestations through that controller. [Sigstore policy-controller](https://docs.sigstore.dev/policy-controller/overview/), [GitHub attestation enforcement](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/enforce-artifact-attestations)

## Stage B: Candidate semantic gaps

1. Bare Kubernetes RBAC authorizes a deployer but does not by itself know build/test provenance.
2. CI knows results but does not control every production deploy caller.
3. A release ticket may add environment-specific rollout or maintenance constraints absent from an image signature.

## Stage C: Policy v0 — attest the digest

```text
ALLOW DEPLOY(cluster, namespace, image_digest)
IFF image_digest has signatures from an allowed builder
AND required tests and vulnerability policy attestations pass.
```

Normal trace: digest D-good is signed and attested; deployment is allowed.

Violating trace: the agent accidentally deploys D-local, which is present in the registry but unattested. Kubernetes RBAC permits the caller; SafeMA denies.

## Stage D: First adversarial critique

The downstream service in the proposed architecture is artificially impoverished. Kubernetes admission is designed to govern API-server behavior, has the actual object operands, covers all callers, and can consult verifiable external supply-chain metadata. A target-native admission policy is more complete than an interceptor around one agent. This candidate is a direct instance of the known “downstream owns semantics” rejection class once admission extensions are counted as part of the downstream platform.

## Stage E: Revision v1 — cross-system release constraints

Add a release manifest saying service S may deploy only digest D to canary, then production only after canary health evidence and within a maintenance window.

```text
ALLOW DEPLOY(production, S, D)
IFF D is attested
AND canary(S,D).health_window_passed
AND change_window(S).open.
```

The policy now joins CI, monitoring, and change calendar facts that Kubernetes does not natively own.

## Stage F: Second adversarial critique

An external admission webhook can retrieve those facts, so the target boundary still dominates. More importantly, canary promotion and rollout health are normal deployment-controller responsibilities. A maintenance-window approval can become stale authorization. Race-free health-sensitive rollout needs a controller that coordinates deployment and rollback, not only a pre-call predicate. SafeMA could implement the webhook, but the application does not motivate a new boundary.

## Three-reviewer test

- **Security reviewer:** conventional signature/attestation admission policy.
- **Systems reviewer:** use an admission controller or rollout controller; it covers bypassing clients.
- **Domain engineer:** this is already how hardened Kubernetes supply chains are built.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: downstream admission should enforce; existing workflow/controller owns invariant; stale authorization risk in the revision.

## Lesson for the next search

“The bare API lacks the fact” is not enough if the platform intentionally exposes a complete admission hook. Search for heterogeneous targets that cannot consume a common fine-grained authority, while remaining alert that this may collapse into classic capability enforcement.

# Application Exploration 5: Attenuated access-request fulfillment

## Stage A: Real application

Identity-governance systems let users request scoped and time-bounded access, route approvals, provision entitlements, and later revoke them. Okta documents conditions defining who can request access, the level, duration, and approval sequence. GitLab's member API exposes the actual project, user, ordered access level, and optional expiry. [Okta Access Requests](https://help.okta.com/oie/en-us/content/topics/identity-governance/access-requests/ar-overview.htm), [GitLab members API](https://docs.gitlab.com/api/project_members/)

The Base App is an access fulfillment agent bridging a service desk/IGA system to heterogeneous SaaS APIs with one broad administrative integration credential. Principals are requester, beneficiary, approver, fulfillment agent, IGA, and target service. Resources are delegation/request, subject mapping, target project, role lattice, expiry, and resulting membership. The consequential operations are create/update membership and grant entitlement.

## Stage B: Candidate semantic gaps

1. GitLab knows whether the integration owner may add members, but not the scope of a separate service-desk decision.
2. The request system knows business approval but may not execute target APIs or share their exact role schema.
3. A broad credential permits many effects; a specific delegation authorizes only a downward-closed subset.

## Stage C: Policy v0 — execute the approved grant

```text
ALLOW GRANT(project, user, role, expiry)
IFF operands exactly equal an active approved request.
```

Normal trace: request AR-19 says Bob/501/Reporter/September 5; exact grant is allowed.

Violating trace: role code confusion yields Maintainer/no expiry; target API allows the Owner credential; SafeMA denies.

## Stage D: First adversarial critique

Exact equality makes this an approval-bound execution example. Cancellation or changed project mappings make it stale authorization. It also fails to express a common property of delegation: an implementation should be allowed to grant less than approved.

## Stage E: Revision v1 — product-order attenuation

```text
ALLOW GRANT(project, principal, level, expires_at)
IFF EXISTS active delegation D:
    principal = D.principal
    AND project in D.resource_scope
    AND level <= D.max_level in an explicit target role lattice
    AND expires_at is present
    AND now < expires_at <= D.not_after.
```

Normal trace: D allows Reporter through September 5; the agent grants Guest through September 4. This is narrower and is allowed.

Violating trace: D allows Reporter on project 501 through September 5; the agent calls GitLab with access level 40 (Maintainer) and omits `expires_at`. GitLab correctly authorizes its Owner credential and valid operands. SafeMA denies both privilege and time amplification.

## Stage F: Second adversarial critique

This is crisp, realistic, and not recommendation routing. It is also textbook capability attenuation/reference monitoring. Okta and other IGA/PAM systems already connect approval to provisioning and expiration; target-native short-lived credentials would be architecturally superior. If an organization has one mature IGA controlling the target, SafeMA adds little.

The strongest remaining version is heterogeneous: one trusted delegation must constrain GitLab, cloud consoles, databases, and legacy tools that cannot accept the same task capability. SafeMA normalizes actual grant operands across adapters. That is useful engineering, but the interesting idea is still classic privilege/resource/time attenuation rather than application-specific semantics.

## Stage G: Revision v2 — heterogeneous grant gateway, final attack

Suppose a delegation contains a principal, a set of resource URNs, a privilege ceiling per target lattice, and an expiry ceiling. SafeMA maps each target's actual grant call into this common product order. This avoids exact approval and demonstrates a general policy abstraction.

The attack remains decisive for this search: a well-engineered non-agentic system would call this an entitlement-provisioning gateway or policy enforcement point. Removing “agent” and “SafeMA” leaves a familiar IGA/PAM architecture. It is a good mechanism-validation example, but it does not expose an under-served application boundary comparable to recovery.

## Three-reviewer test

- **Security reviewer:** classic least privilege, capability attenuation, and a reference monitor.
- **Systems reviewer:** a common provisioning gateway is sensible but not specifically an agent-safety contribution.
- **Domain engineer:** real and useful where connectors are heterogeneous, but mature IGA suites already aim to do this.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reason: classic security mechanism with too little new application structure. Retain it as a supporting policy-language test, not the flagship second application.

## Lesson for the next search

A scenario may have a real semantic gap, deterministic policy, and clear consequence yet still be unconvincing because the traditional mechanism is exactly the proposed architecture. Search next for application semantics that cut across heterogeneous services, but test whether records-management platforms already own them.

## Checkpoint comparison after five families

Recovery remains the only survivor. Access fulfillment is easier to implement but easier to dismiss as a classic reference monitor. CI/CD is easier to explain but the natural enforcement boundary is already deployed at the downstream API server. Payment remains interesting because of its numeric/history predicate, though its AP-module objection is stronger than recovery's orchestrator objection: an orchestrator can be separated from a narrow destruction interlock, whereas invoice matching is the core domain operation.

# Application Exploration 6: Cross-SaaS legal-hold-aware cleanup

## Stage A: Real application

Organizations retain and dispose of records according to retention schedules and legal/eDiscovery holds. Microsoft Purview documents that retention preserves copies when users edit or delete content, that preservation takes precedence over deletion, and that eDiscovery holds preserve content until manually released. Preservation Lock can prevent even an administrator from weakening a retention policy. [Microsoft retention](https://learn.microsoft.com/en-us/purview/retention), [Purview holds](https://learn.microsoft.com/en-us/purview/edisc-hold-manage), [Preservation Lock](https://learn.microsoft.com/en-us/purview/retention-preservation-lock)

The proposed Base App is a lifecycle/cleanup agent that inventories expired records across CRM, support, document, and collaboration services and invokes their purge APIs. Principals are records manager, legal case team, data owner, cleanup agent, SaaS administrators, and SaaS services. Resources are records, custodians, classes, retention deadlines, hold selectors, and permanent-delete effects.

Native controls matter greatly. In Microsoft 365, a user-visible deletion can succeed while a preserved copy remains, and some deletion operations are blocked. That is stronger than an agent-specific interceptor because it covers all callers and keeps preservation state in the service that stores the data.

## Stage B: Candidate semantic gaps

1. A central legal case may name custodians or record classes spanning many SaaS products.
2. A generic CRM purge API can authorize an administrator while not knowing an external case system's hold.
3. A retention system may know holds but not the actual object IDs and delete calls in every target.
4. Preservation can require a deny-overrides join across current record classification and multiple active selectors.

## Stage C: Policy v0 — block deletion under a central hold

```text
ALLOW PURGE(service, record_id)
IFF retention_deadline(record_id) <= now
AND no active legal hold selector matches record_id.
```

Normal trace: ticket T-9 is seven years old, its retention period elapsed, and no hold matches; purge is allowed.

Violating trace: T-10 is old but belongs to custodian Alice, who is covered by case L-77. The CRM admin credential may permanently purge T-10; SafeMA denies.

## Stage D: First adversarial critique

Within a service such as Microsoft 365, this is plainly downstream-owned records logic. Native preservation is harder to bypass and has richer semantics for recoverable items, copies, labels, holds, and locked policies. Putting SafeMA only in front of one cleanup agent would provide a weaker guarantee.

Record identity and selector matching are also harder than they appear: aliases change, custodians have multiple accounts, attachments and copies may not inherit labels, and hold propagation is asynchronous. If SafeMA trusts the cleanup agent's `custodian=Alice` claim, the boundary is hollow.

Policy v0 is rejected for any target with adequate native retention/hold support.

## Stage E: Revision v1 — heterogeneous-service preservation gateway

Restrict the case to targets lacking compatible native holds. An independent inventory/classification connector produces trusted records binding target-native IDs to custodian, record class, and retention start event. A central legal system produces signed active/released hold selectors. SafeMA normalizes every modeled permanent-delete call.

```text
ALLOW PERMANENT_DELETE(target, native_record_id)
IFF a current trusted record mapping exists
AND record.retention_deadline <= now
AND NOT EXISTS active hold H where H.selector matches record
AND target deletion mode is actually irreversible.
```

Unknown mappings fail closed. Deletion success creates an auditable disposition event.

Normal trace: expired CRM case C-44 has a current mapping and no matching hold; allow.

Violating trace: the central case system added a hold for Alice, and trusted inventory maps C-45 to Alice. The CRM has no legal-hold feature but accepts the admin purge. SafeMA denies.

## Stage F: Second adversarial critique

The refined gap is real, but the obvious non-agentic owner is an enterprise records/eDiscovery platform or deletion gateway. SafeMA can instantiate that gateway, yet the domain already names the component. More seriously, preventing the modeled delete call is not preservation unless all other admin/UI/API deletion paths are covered. Exporting held records to an immutable archive may be safer than trusting interception across heterogeneous SaaS products.

This candidate also inherits a hard “inventory completeness” problem from key destruction. A current mapping for one object is positive evidence, but a custodian-scoped hold must find every relevant copy. The policy can protect known objects without claiming complete legal compliance, but that narrower guarantee is less compelling.

## Three-reviewer test

- **Security reviewer:** structured deny-overrides access control over delete, not IFC if classifications are trusted; completeness resembles data governance.
- **Systems reviewer:** deploy records-management connectors and an immutable archive; an app-local interceptor is insufficient.
- **Domain engineer:** holds and retention are real, but serious platforms already implement them natively and legal preservation cannot depend on one agent path.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: downstream should enforce where capable; existing records-management component owns the invariant elsewhere; incomplete enforcement boundary across heterogeneous services.

## Lesson for the next search

Cross-SaaS context can create a semantic gap while still demanding organization-wide path coverage that SafeMA's modeled agent effects do not automatically provide. Explore a physical command where the protected path is narrower, but ask whether the result is merely delegated access.

# Application Exploration 7: Rental-fleet vehicle commands

## Stage A: Real application

Connected-vehicle APIs expose real physical commands. Tesla's Fleet API includes door unlock, trunk actuation, remote start-related scopes, guest mode, and driver management. Commands may be signed by an application's virtual key; the vehicle verifies that signature. Tesla also documents guest access that can be removed and some command-specific local-state checks, such as requiring the vehicle to be parked. [Tesla vehicle commands](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands), [virtual keys](https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide), [authentication scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview)

The Base App is a rental or car-share support agent. Principals are renter, fleet operator, support agent, vehicle owner, and vehicle platform. Resources are reservation, verified customer, VIN, rental interval, pickup zone, handoff credential, and physical command. Consequential effects are unlock, add driver, remote start, clear drive PIN, and erase user data.

The vehicle/platform owns cryptographic command authorization and local safety preconditions. The rental service owns customer, booking, payment, and assigned-vehicle semantics.

## Stage B: Candidate semantic gaps

1. A fleet-manager key may validly command every vehicle while one renter is assigned only one VIN.
2. The vehicle knows it is parked and that the command is signed, but not whether a rental is active.
3. The booking service knows the rental but does not itself actuate the vehicle.
4. Support workflows may need exceptional access that ordinary renter capabilities do not cover.

## Stage C: Policy v0 — active-reservation binding

```text
ALLOW UNLOCK(VIN)
IFF EXISTS active reservation R:
    R.customer = authenticated_requester
    AND R.VIN = VIN
    AND R.start <= now <= R.end.
```

Normal trace: Alice's active booking is for VIN-A; unlock VIN-A is allowed.

Violating trace: an agent confuses adjacent bookings and commands VIN-B. The signed fleet-manager command is valid, so the platform allows; SafeMA denies the VIN/reservation mismatch.

## Stage D: First adversarial critique

This is recommendation-letter binding with a physical actuator: customer-scoped authority must go to the matching vehicle/context while active. It is also ordinary access control. The cleaner design is to provision a narrow time-bound virtual key or guest access to the renter, eliminating the broad fleet credential from the routine path.

The identity of `authenticated_requester` is problematic when the Base App is acting on a chat or support message. If SafeMA trusts the agent's claim about the customer, it does not independently enforce anything. If a front end authenticates the user and mints a capability, the case becomes capability consumption.

## Stage E: Revision v1 — physical handoff envelope

Try a richer policy using independent booking and telemetry facts:

```text
ALLOW ENABLE_GUEST_ACCESS(VIN, customer)
IFF reservation(customer,VIN) is active
AND vehicle location is within the pickup geofence
AND vehicle state = PARKED
AND a one-use handoff nonce from the kiosk matches reservation
AND no other guest assignment is active.
```

This adds physical-world state, exclusivity, and one-use evidence. A wrong-customer or wrong-location command is denied even though the fleet API accepts the operator.

## Stage F: Second adversarial critique

Vehicle-local state checks such as `PARKED` belong in the vehicle platform, and telemetry/geofence readings can be stale. Booking, kiosk, and key provisioning are normal car-share access-control components. The one-use handoff nonce is precisely a capability. SafeMA could offer a reusable enforcement framework, but the application structure remains principal/resource/time binding plus classic physical access control.

The consequence is clear, yet the baseline recommendation example already explains “right object to right beneficiary while request active” more cleanly and without personal-safety complications.

## Three-reviewer test

- **Security reviewer:** time-bound capability and physical access control.
- **Systems reviewer:** issue a per-rental virtual key; do not keep a broad fleet key in the normal agent path.
- **Domain engineer:** fleet commands and booking separation are real, but telemetry freshness and emergency support exceptions complicate a crisp policy.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: ordinary access control/capability; too similar to recommendation binding; physical-state freshness complicates assurance.

## Lesson for the next search

Moving a binding policy into the physical world raises consequence but does not change its structure. Search next for a genuine purpose/derivation policy, while being willing to reject it if reliable enforcement requires semantic IFC.

# Application Exploration 8: Purpose-limited research or health-data export

## Stage A: Real application

Research and regulated-data workflows collect datasets under stated purposes, combine or transform them, and export results to collaborators or analysis environments. Purpose limitation is a real governance principle; the UK ICO says personal data should be collected for specified, explicit, legitimate purposes and further use requires compatibility analysis. HHS describes “minimum necessary” policies for many non-treatment uses and disclosures of protected health information. [ICO purpose limitation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/purpose-limitation), [HHS minimum necessary](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html)

The Base App is a research assistant that queries datasets, joins/aggregates them, generates tables or summaries, and uploads outputs to a collaboration store. Principals are data subjects, data custodian, researcher, IRB/privacy board, collaborator, agent, warehouse, and destination. Resources are source datasets, use restrictions, study protocol, query/run lineage, derived artifacts, disclosure-risk assessments, and export calls.

Real lineage services track some structured derivations, but coverage is partial. Google documents that its lineage records metadata rather than data, retains records for a limited period, and has product-, table-, and column-level coverage limitations. [Google data-lineage limitations](https://docs.cloud.google.com/dataplex/docs/about-data-lineage)

## Stage B: Candidate semantic gaps

1. A destination store can authorize an upload but not know all datasets that contributed to the bytes.
2. A warehouse may authorize each query but not know the ultimate external purpose.
3. Restrictions from multiple inputs may compose into a stricter output policy.
4. De-identification or aggregation may legitimately declassify an output, but that fact is transformation-specific.

## Stage C: Policy v0 — inherited purpose intersection

```text
ALLOW EXPORT(output, destination, declared_purpose)
IFF for every input dataset in lineage(output):
    declared_purpose is allowed
    AND destination class is allowed.
```

Normal trace: an aggregate derived only from datasets allowing academic study S is uploaded to S's approved enclave.

Violating trace: an output includes a noncommercial dataset but is uploaded to a commercial partner. The store accepts the uploader; SafeMA denies based on lineage restrictions.

## Stage D: First adversarial critique

This is semantic information-flow control. SafeMA must know complete lineage even across LLM summaries, copied snippets, local files, and transformations. If the Base App supplies the lineage, it can omit the inconvenient input. If SafeMA mediates all reads, writes, model context, and transformations, the project expands into end-to-end taint tracking.

Conservative label union also overtaints. A formally approved aggregate or de-identified result may be releasable even though raw inputs were restricted. Deciding whether arbitrary generated text leaks protected meaning is precisely the blind-review failure class. Policy v0 is rejected.

## Stage E: Revision v1 — release-certified export artifacts only

Move declassification out of SafeMA. A trusted disclosure-review job produces an immutable artifact digest and a structured release certificate naming allowed study purposes and destination classes.

```text
ALLOW EXPORT(actual_digest, destination, purpose)
IFF a current release certificate binds actual_digest
AND purpose in certificate.allowed_purposes
AND destination.class in certificate.allowed_destinations.
```

Normal trace: digest D-approved is released for study S to enclave class E; allow.

Violating trace: the agent uploads an earlier unreviewed digest or sends D-approved to a public bucket; downstream storage allows, SafeMA denies.

## Stage F: Second adversarial critique

The revision is enforceable, but it has intentionally discarded the interesting derivation problem. It is now a certified artifact bound to an allowed purpose/destination—very close to the recommendation-letter policy and package provenance. The independent review service owns the substantive de-identification and purpose decision; SafeMA only checks the certificate's use.

## Three-reviewer test

- **Security reviewer:** v0 is IFC with difficult declassification; v1 is signed-label enforcement.
- **Systems reviewer:** reliable v0 requires whole-pipeline mediation; v1 is a release gateway but not a new policy shape.
- **Domain engineer:** purpose limitation is real, but legal compatibility and de-identification are context-dependent and exception-rich.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: v0 requires semantic IFC; v1 collapses into provenance/artifact-to-destination binding.

## Lesson for the next search

Moving ambiguous semantics into a trusted certificate can make enforcement deterministic, but it may also remove the feature that made the application distinct. Search for a structured cross-system entitlement with independently observable physical/business evidence and compare it against the already stronger AP case.

## Checkpoint comparison after eight families

None of applications 4–8 displaces recovery. CI/CD and legal holds have stronger native/platform boundaries; identity and fleet are classical attenuation/binding; research export requires IFC or collapses into certified-artifact routing. The search is converging on a pattern: positive cross-service preservation witnesses are more compelling than labels that merely authorize a destination or negative claims over an incompletely observed universe.

# Application Exploration 9: Return-qualified customer refund

## Stage A: Real application

Customer-return workflows create a return intent, arrange reverse fulfillment, receive or inspect goods, choose a disposition, and issue a refund. Shopify models returns, reverse fulfillment, status, line quantities, processing, dispositions, and optional refunds in one platform. Stripe's generic refund API instead primarily enforces payment-rail facts: a refund names a charge or payment intent and cannot exceed the remaining unrefunded charge amount. [Shopify Return](https://shopify.dev/docs/api/admin-graphql/latest/objects/Return), [Stripe refund API](https://docs.stripe.com/api/refunds/create)

The Base App is a support agent spanning a ticket system, warehouse returns system, commerce order service, and payment processor. Principals are customer, support agent, warehouse operator, merchant, and processor. Resources are order lines, return authorization, carrier/warehouse events, inspection outcome, original charge, prior refunds, and actual refund amount. Consequential effects are issuing money and restocking or disposing inventory.

If Shopify or another commerce platform owns order, return, disposition, and refund, it is the natural invariant owner. The candidate is plausible only when warehouse and payment systems are split.

## Stage B: Candidate semantic gaps

1. A processor knows the charge and remaining refundable balance but not whether goods were received or accepted.
2. A support system knows customer communication but not physical receipt.
3. A warehouse knows item/quantity/condition but not captured payment and prior refunds.
4. A valid processor refund can still violate merchant return policy.

## Stage C: Policy v0 — refund approved tickets

```text
ALLOW REFUND(charge, amount)
IFF support_ticket.status = APPROVED
AND ticket.expected_refund = (charge, amount).
```

Normal trace: an approved $100 refund is issued exactly.

Violating trace: the agent issues $150; processor balance permits it; SafeMA denies.

## Stage D: First adversarial critique

This is exact approval and potentially stale approval. The support ticket is also likely controlled by the same Base App. It says nothing about the structured business reason for the refund and is weaker than the payment candidate. Policy v0 is rejected.

## Stage E: Revision v1 — live quantity/value entitlement

For a simplified physical-return policy:

```text
ALLOW REFUND(charge, currency, amount, return_id)
IFF trusted return R maps to charge and order
AND warehouse_received_accepted_qty(line) >=
    previously_refunded_return_qty(line) + proposed_qty(line)
AND amount = SUM(proposed_qty * refundable_unit_value)
AND amount <= processor.remaining_unrefunded_amount
AND currency = charge.currency.
```

On success, quantities and value are consumed atomically.

Normal trace: two $50 units are accepted at the warehouse and neither was refunded; $100 is allowed.

Violating trace: a return label exists for two units, but only one is received. The agent confuses “return initiated” with “return accepted” and requests $100. Stripe can correctly allow $100 because the original charge has sufficient remaining value; SafeMA allows at most $50 and denies.

## Stage F: Second adversarial critique

The semantic gap is clean in a split deployment. Nevertheless, the policy is AP three-way matching with roles renamed: order/receipt/refund replaces PO/receipt/payment, with the same quantitative bound and consumption. Shopify's integrated model also shows that a commerce platform can naturally own return and refund processing. Refund exceptions—refund without return, damaged-item concessions, shipping, tax, fraud, partial goodwill—make a universal hard rule less realistic than the simple trace suggests.

Narrowing to a product category that always requires warehouse acceptance improves realism but does not improve conceptual diversity. It remains useful as corroboration that quantitative effect authority recurs across domains, not as a separate flagship.

## Three-reviewer test

- **Security reviewer:** numeric one-use entitlement, essentially a bounded capability.
- **Systems reviewer:** use the commerce/returns service as the source of a narrow refund command.
- **Domain engineer:** many legitimate refunds do not require receipt, so policy scope must be product/reason-specific.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: dominated by the AP application's policy shape; integrated commerce service often owns the invariant; exceptions weaken a universal rule.

## Lesson for the next search

Finding the same quantitative pattern in another domain increases confidence that numeric consumption is generalizable, but it does not create a diverse second application. Spend the final planned family on a truly global multi-resource invariant and test whether enforcement needs coordination beyond a runtime guard.

# Application Exploration 10: Redundancy-preserving infrastructure termination

## Stage A: Real application

Infrastructure controllers replace, evict, drain, and terminate compute while maintaining availability. Kubernetes PodDisruptionBudgets constrain voluntary evictions using `minAvailable` or `maxUnavailable`, but explicitly do not guarantee availability against involuntary failures. EC2 Auto Scaling instance maintenance and refresh policies similarly maintain minimum healthy percentages during managed replacement. Terraform provides `prevent_destroy`, but its documentation notes that removing the resource configuration also removes that protection. [Kubernetes disruption budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/), [EC2 instance refresh](https://docs.aws.amazon.com/autoscaling/ec2/userguide/instance-refresh-overview.html), [Terraform lifecycle](https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle)

The candidate Base App is a multi-cloud decommissioning agent that terminates instances across providers. Principals are service owner, SRE, agent, cloud providers, scheduler/controller, and monitoring system. Resources are service membership, replicas, health, failure domains, in-flight drains/terminations, and provider termination APIs. The consequential operation is terminating the actual instance.

Within one cluster or autoscaling group, native controllers own much of the relevant state. A cross-provider service-level objective may span them and be absent from any one cloud.

## Stage B: Candidate semantic gaps

1. Provider A can authorize deletion of its instance but cannot see provider B's healthy replicas.
2. Monitoring sees health but does not serialize destructive actions.
3. Service discovery sees membership but may lag terminations and failures.
4. The application policy may require both a minimum replica count and failure-domain diversity.

## Stage C: Policy v0 — check the post-effect topology

```text
ALLOW TERMINATE(instance i)
IFF healthy_replicas(service(i) \ {i}) >= N
AND distinct_failure_domains(service(i) \ {i}) >= K.
```

Normal trace: four healthy replicas span three providers; N=3 and K=2; terminating one still satisfies both.

Violating trace: i is the only healthy replica in provider B; the call would retain count N but reduce diversity below K. Provider B's IAM allows termination; SafeMA denies.

## Stage D: First adversarial critique

This is a read-check-act race. Another replica can fail or another agent can terminate concurrently after SafeMA checks but before the provider effect. Health is inherently time-varying and monitors can be stale. A pre-call interceptor cannot truthfully guarantee the postcondition.

Within one Kubernetes cluster or autoscaling group, the target's controller/admission path is already better placed. Across providers, the policy is real but the system needs a global coordinator, not just a metastore query.

## Stage E: Revision v1 — leases and disruption reservations

Introduce a trusted global disruption coordinator. Before termination, SafeMA atomically reserves one unit of disruption budget for the service/failure domain. The reservation excludes other managed terminations until commit or timeout.

```text
ALLOW TERMINATE(i) only after atomic RESERVE(service(i), domain(i), i)
where committed + reserved removals preserve N and K
under coordinator-owned membership epochs.
```

Normal trace: the reservation serializes two agents; only the first termination fits the budget.

Violating trace: another agent already holds the last available disruption slot; provider IAM would permit both calls, but SafeMA denies the second.

## Stage F: Second adversarial critique

Reservations solve concurrent planned operations but not involuntary failure after reservation. Stronger guarantees require leases on membership, health/failure detectors, controller cooperation, rollback/replacement, and reconciliation. At that point the “SafeMA extension” is a distributed availability controller. Kubernetes documentation's explicit distinction between voluntary and involuntary disruptions confirms this limitation.

The candidate remains valuable as a boundary marker: some semantic policies are not safety predicates over a single effect; they are coordination protocols. SafeMA could integrate with an existing coordinator and enforce possession of a reservation at each provider call, but then the coordinator owns the substantive invariant and SafeMA consumes a capability.

## Three-reviewer test

- **Security reviewer:** history- and state-dependent reference monitor with reservations; no IFC issue.
- **Systems reviewer:** availability is a distributed-control problem; use a controller with leases and reconciliation.
- **Domain engineer:** native groups handle local maintenance; cross-cloud membership and health semantics are deployment-specific and exception-rich.

## Final verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: race-free enforcement requires a distributed transaction/coordination mechanism; native controllers own local variants; the modest SafeMA extension would not support the claimed guarantee.

## Lesson for the next search

The search has converged enough to stop at ten families. A crisp predicate is not enforceable merely because it can be evaluated; if truth can change concurrently and the effect changes the predicate, the mechanism must reserve or coordinate. Recovery survives partly because it is one-sided: false denial leaks cost, while independently locked retention makes the positive witness stable during the destructive action.

## Rejection Taxonomy

### Downstream platform owns the semantics or has the right complete hook

- HotCRP reviewer conflicts, visibility, roles, decisions, and phases
- Kubernetes image signature/attestation admission
- Single-platform Microsoft 365 retention and eDiscovery holds
- Single-cluster disruption budgets and autoscaling maintenance

### Existing vertical application or workflow component owns the invariant

- Integrated ERP three-way matching and invoice holds
- Integrated commerce return processing and refunds
- Deployment rollout/canary controller
- Enterprise records/eDiscovery platform

### Merely provenance/resource-to-destination binding

- HotCRP cross-paper contamination
- Release-certified research-data artifact export
- Package-publication provenance from the earlier survey
- Permit/material shipment from the earlier survey
- Basic rental-reservation-to-VIN command binding

### Requires semantic information flow or declassification

- Blind-review prose leakage
- Derived research/health-data purpose restriction
- Arbitrary LLM-generated output disclosure review

### Stale or exact authorization redux

- Approved HotCRP batch
- “Pay approved invoice” v0
- Exact approved access grant v0
- Support-ticket-approved refund v0
- Maintenance-window release formulations

### Classic security mechanism with little new application structure

- Resource/privilege/time attenuation for access grants
- Per-rental time-bound vehicle key
- Verifier-minted one-use payment capability, considered alone

### Incomplete-universe or untrustworthy-negative-evidence problem

- “No recent key use, therefore safe to destroy”
- Universal key-to-ciphertext dependency inventory
- Organization-wide custodian hold coverage across unknown SaaS copies
- Absence of derived-data influence without whole-pipeline mediation

### Needs coordination, not a pre-effect predicate

- Multi-cloud healthy-capacity/failure-domain preservation
- Any concurrent quantitative consumption without reservation
- Cross-system atomicity claims against simultaneous failure

### Unrealistic or exception-dominated policy

- Mandatory warehouse receipt for every refund
- Travel constraints treated as immutable policy in the earlier survey
- Manufactured conference separation of duty

### Dominated by a stronger candidate of the same shape

- Return-qualified refund is dominated by AP's multi-record quantitative obligation
- Incident-evidence preservation from the earlier survey is subsumed by recovery/hold analysis
- Fleet binding is less distinctive than recommendation submission

## How the taxonomy evolved

1. **Before Exploration 1:** inherited downstream-ownership, stale-authorization, artifact-binding, semantic-IFC, and unrealistic-policy classes from HotCRP.
2. **After payment:** added “vertical application module owns the join.” Cross-system distribution alone no longer counted as sufficient.
3. **After recovery:** separated positive preservation witnesses from mere workflow status and introduced “orchestrator versus narrow interlock” as a boundary test.
4. **After key destruction:** added incomplete-universe/negative-evidence failures. An apparently precise predicate can rest on an unverifiable completeness assumption.
5. **After CI/CD:** expanded downstream ownership to include an official admission extension, not only built-in business logic.
6. **After access fulfillment:** added “classic security mechanism with little new application structure.” A valid SafeMA use need not be a compelling research case.
7. **After legal holds:** distinguished checking known objects from claiming organization-wide path/record coverage.
8. **After fleet:** added “physical consequence does not create structural novelty.”
9. **After research export:** recorded that external certification may make a rule crisp by collapsing it into an already-known artifact-binding shape.
10. **After refunds:** added domination by a stronger application with the same policy algebra.
11. **After infrastructure termination:** added the coordination class and separated evaluable predicates from enforceable invariants.

## Emerging Characteristics of Strong SafeMA Applications

1. **The best gap is asymmetric and legitimate.** The effect service owns caller authority and local validity; another authority owns a fact the effect service should not absorb.
2. **Positive, stable witnesses beat absence claims.** “A restore-tested retained replica of v37 exists” is more defensible than “nothing depends on key K.”
3. **The consequential operand must be immutable or boundary-resolved.** Version/digest identity avoids relying on Base App job IDs, paths, or `validated=true` flags.
4. **A narrow invariant is different from an orchestrator.** SafeMA is most credible when it can deny an unsafe terminal effect without taking over scheduling, retries, planning, or compensation.
5. **Cross-system distribution is necessary in many strong cases but not sufficient.** If a canonical domain module such as AP matching naturally owns the join, SafeMA needs an additional independence argument.
6. **Target-native admission wins when it is complete.** A downstream admission controller that sees actual operands and covers all callers is usually preferable.
7. **Determinism is not enforceability.** Numeric or cardinality formulas still need reservation/serialization when concurrent effects can consume the same authority.
8. **Trusted evidence contracts are part of the policy.** The source, identity binding, freshness/revocation behavior, and failure mode of a certificate matter as much as its fields.
9. **Moving judgment to a certificate has a cost.** It can keep SafeMA small, but may turn a distinct semantic problem into ordinary signed-label/capability consumption.
10. **A good research application teaches a policy algebra.** Recovery contributes preservation under destruction; payment contributes relational numeric consumption; recommendation contributes semantic artifact/context binding.

## Mechanism implications without optimizing for the current prototype

| Candidate | Needed mechanism | Scope assessment |
|---|---|---|
| Recovery before destruction | destructive effect kind; version/digest identity; trusted multi-origin event records; certificate/revocation; retention-time comparison | Small-to-moderate, generalizable extension |
| Three-way-match payment | exact decimal money; relational joins; aggregation; history; transactional reservation/consumption | Moderate, generalizable, concurrency-sensitive |
| Key destruction | universal set containment; authoritative complete inventory; disable/observe history; hold joins | Large unless SafeMA already controls the whole key-use universe |
| Multi-cloud termination | global membership epochs; leases; health/failure detection; reconciliation | Large new distributed-systems project |
| Derived-data export | end-to-end provenance propagation and declassification | Large new semantic-IFC project |

## Final stopping-condition audit for the leading recovery case

| Required property | Assessment |
|---|---|
| Realistic workflow and policy | Yes, for cross-account/provider decommission of an immutable snapshot, not generic “every delete needs a restore test” |
| Consequential, easy violation | Yes: deleting the last source copy without a working retained recovery point |
| Downstream correctly allows | Yes: source IAM and local deletion state are satisfied |
| Downstream should not own missing fact | Yes: a retiring source provider should not adjudicate another provider/account's restore validation |
| Higher-level context exists | Yes: migration, backup, verifier, retention, and failure-domain records |
| Independent runtime boundary adds value | Yes: it protects all modeled destructive calls from the faulty migration agent |
| Deterministic policy | Yes, conditional on the recovery authority's explicit certificate contract |
| Not recommendation routing | Yes: preservation witness gates destruction |
| Not stale approval | Yes: the main counterexample never acquired valid recovery evidence; current certificate status is checked at effect time |
| Not downstream ACL bug | Yes |
| No semantic IFC | Yes |
| New dimension | Yes: cross-service recovery existence and retention before destruction |
| Locally mockable | Yes: source, archive, verifier, and metastore can be local services |
| No one-line architectural dismissal | Qualified yes: “use a backup orchestrator” does not eliminate the value of an independent deny-only last-copy interlock, but this remains the strongest objection |

The case should claim conditional enforcement over modeled destructive APIs and trusted evidence—not universal backup correctness, protection against simultaneous catastrophic loss, or proof that every application-level datum is usable.

## Final synthesis

### A. What was learned

1. The most compelling SafeMA boundary is not merely between two services; it is between a generic consequential effect and a stable semantic witness owned elsewhere.
2. Native downstream admission or preservation usually beats an agent-local monitor because it covers every caller.
3. A canonical vertical module can defeat a cross-system story even when the payment/storage API lacks the facts.
4. Positive evidence is much safer than inferring a universal negative from telemetry or inventory.
5. Immutable effect identity plus an independently minted certificate gives a clean, testable trust boundary.
6. Capability attenuation is useful but too classical to carry the application argument alone.
7. Derived-content purpose policies quickly become semantic IFC; certification makes them tractable but often too similar to recommendation routing.
8. Concurrent consumption and global availability are protocols, not just predicates.
9. Destruction policies are especially natural when SafeMA is one-sided: conservative denial costs time/storage, while a false allow causes irreversible loss.
10. The recovery case motivates a persistent metastore for long-running cross-service evidence more naturally than short-lived request checks.

### B. Strongest surviving applications

#### 1. Cross-provider recovery before destructive decommissioning

**Application:** Retire an old storage/database administrative domain after migrating one immutable dataset snapshot.

**Normal workflow:** Freeze/version source snapshot; copy it to a separately administered provider/account; restore it into a disposable environment; validate; lock retention; delete the last source-side copy.

**Base App:** Migration/decommissioning agent.

**External services:** Source storage/database, destination backup/archive, restore runner/validator, retention service.

**Exact policy:** Allow `DESTROY_LAST_SOURCE_COPY(dataset, version, digest)` iff a current non-revoked recovery certificate binds that exact tuple to an available destination recovery point, successful restore validation, a different administrative/failure domain, and retention through the rollback window.

**Concrete violation trace:** Copy job reports complete, but restore validation fails because the destination lacks the encryption key. The agent calls delete on v37/D37 anyway. Source IAM allows; SafeMA finds no valid certificate and denies.

**Why downstream allows:** The caller is an authorized administrator and the source snapshot is locally deletable.

**Why downstream should not enforce the application property:** The retiring source should not need credentials into, or semantics for, another provider/account's backup and validation systems.

**Why Base App checks alone are insufficient:** The migration agent can confuse transfer completion with recoverability, join the wrong version, or skip validation.

**SafeMA enforcement point:** Immediately before the actual final-snapshot/version destroy call, with boundary-resolved version and digest.

**Required trusted metadata/evidence:** Source immutable identity/digest; destination recovery-point identity and availability; recovery-authority certificate; retention/failure domain; revocation events.

**Difference from recommendation-letter app:** It is preservation under destruction, not semantic artifact-to-request/destination routing.

**Difference from stale-approval examples:** No earlier approved plan is required. The bad trace never had a valid recovery witness.

**Closest traditional mechanism:** Backup/decommissioning safety interlock or verifier-minted capability.

**Why SafeMA is still interesting:** A small, reusable, deny-only boundary can enforce the same invariant across heterogeneous destructive APIs without becoming the migration orchestrator.

**Strongest remaining objection:** A competent backup orchestrator should already enforce it; the paper must make the independent interlock and cross-administrative evidence boundary explicit.

#### 2. Cross-system three-way-match payment guard

**Application:** Pay supplier invoices using disjoint procurement, warehouse, invoice-intake, and payout systems.

**Normal workflow:** Match invoice lines to PO price and received-not-reversed quantity, bind the vendor bank account, then transfer and consume the payable quantity/value.

**Base App:** Accounts-payable integration agent.

**External services:** Procurement, receiving, invoice intake, vendor master, and generic payment rail.

**Exact policy:** Allow `PAY(payee, currency, amount, invoice_ref)` iff trusted records form one current unpaid obligation, actual payee/currency match, each line's price matches its PO, prior paid plus proposed quantity does not exceed received-not-reversed quantity, the amount equals the line sum, and the invoice/quantities can be atomically consumed.

**Concrete violation trace:** PO orders 100 drives at $120, but only 60 were received. The agent transfers $12,000. The payment rail allows an authorized funded transfer; SafeMA caps current matched value at $7,200 and denies.

**Why downstream allows:** The payment rail owns account authority, rail validity, and funds, not the payer's PO/receipt semantics.

**Why downstream should not enforce the application property:** A generic rail should not import each customer's procurement and warehouse model.

**Why Base App checks alone are insufficient:** A wrong join or skipped quantity check becomes an irreversible transfer under a broad credential.

**SafeMA enforcement point:** Immediately before the transfer API, with reservation and post-success consumption.

**Required trusted metadata/evidence:** PO/amendment events, receipts/reversals, authenticated invoices, vendor-bank mapping, prior successful payments, canonical money arithmetic.

**Difference from recommendation-letter app:** Relational aggregation, numeric bounds, and consumable authority replace artifact/context equality.

**Difference from stale-approval examples:** The payment is invalid in a static world; no intervening change or exact approval is needed.

**Closest traditional mechanism:** ERP/AP three-way matcher plus payment hold, or a bounded one-use payment capability.

**Why SafeMA is still interesting:** It demonstrates a general quantitative/history policy at a generic effect rail and provides fault independence from agent reasoning.

**Strongest remaining objection:** In a well-engineered deployment, an AP service naturally owns exactly this invariant; the split architecture may look selected to evade that fact.

#### 3. Key-destruction blast-radius guard

**Application:** Rotate or cryptographically erase a tenant's data by scheduling KMS key-version destruction.

**Normal workflow:** Enumerate key dependencies, rewrap or authorize erasure of every in-scope object, disable and observe when preserving data, then schedule destruction with a waiting period.

**Base App:** Key-lifecycle/privacy-offboarding agent.

**External services:** KMS, storage systems, tenancy registry, records/hold authority, and inventory/probe system.

**Exact policy:** For the bounded crypto-erasure version, allow `SCHEDULE_KEY_DESTRUCTION(K)` iff an active deletion authority names tenant T; K is dedicated to T; every registered K-wrapped object lies in T's deletion cohort; none is retained/held; no registered recoverable alternate wrapping defeats the erasure claim; and the waiting period meets policy.

**Concrete violation trace:** K-73 also protects a shared billing archive. The authorized key administrator schedules deletion; KMS allows; SafeMA's key/object set shows collateral data and denies.

**Why downstream allows:** KMS correctly enforces key-admin authority and waiting-period constraints.

**Why downstream should not enforce the application property:** KMS should not own tenant, legal-hold, and cross-storage object semantics.

**Why Base App checks alone are insufficient:** A faulty inventory join can cause permanent loss or incomplete erasure.

**SafeMA enforcement point:** Before scheduling destruction, since scheduling disables the key and leads automatically to destruction.

**Required trusted metadata/evidence:** Authoritative key-to-tenant mapping, closed-world key-to-object inventory, deletion cohort, holds/retention, alternate wrapping keys, waiting period.

**Difference from recommendation-letter app:** Universal blast-radius containment and intentional cryptographic destruction, not routing.

**Difference from stale-approval examples:** The central failure is collateral set membership, not changed state after approval.

**Closest traditional mechanism:** KMS governance, cryptographic-erasure controller, and disable-observe-delete runbook.

**Why SafeMA is still interesting:** It exposes a crisp cross-system semantic gap at an irreversible API and tests universal set-containment policy.

**Strongest remaining objection:** No general system can prove the key-use inventory complete. The case is defensible only in a closed world where all wrapping paths are mediated; that may be too large for SafeMA.

### C. Rejected application families

| Application family | Best idea attempted | Why it ultimately failed | What was learned |
|---|---|---|---|
| Conference management / HotCRP | Cross-paper leakage or conflict/phase enforcement | Native service owns crisp facts; remaining leakage needs IFC or duplicates recommendation binding | Rich SaaS can know too much to yield a SafeMA gap |
| Attested CI/CD deployment | Require attested digest plus canary health | Kubernetes admission and rollout controllers are the better complete boundary | Count official admission extensions as downstream enforcement |
| Access-request fulfillment | Resource/role/time attenuation across SaaS APIs | Correct but classical IGA/PAM/capability enforcement | A useful policy primitive is not automatically a novel application |
| Cross-SaaS records cleanup | Central hold overrides permanent delete | Native holds win where present; heterogeneous path/inventory completeness is weak | Legal preservation needs coverage of all copies and delete paths |
| Rental-fleet commands | Active booking + geofence + one-use handoff gates guest access | Ordinary physical access capability; close to recommendation binding; stale telemetry | Physical consequence does not change policy shape |
| Purpose-limited data export | Compose input restrictions over derived output | Needs whole-pipeline semantic IFC; certification collapses to artifact routing | Crisp certificates can erase the distinct research problem |
| Return-qualified refund | Warehouse-accepted quantity bounds refund | Same quantitative shape as AP, with more exceptions; integrated commerce can own it | Use domination to avoid counting domain renamings |
| Multi-cloud termination | Preserve N healthy replicas in K failure domains | Race-free guarantee needs leases, failure detection, and a controller | Some invariants are protocols rather than pre-effect predicates |
| Package release (earlier survey) | Publish only attested build to namespace/version | Native trusted publishing/provenance; artifact/context similarity | Supply-chain evidence is strongest at registry/admission boundaries |
| Travel booking (earlier survey) | Enforce budget and temporal itinerary feasibility | Trusted user-intent capture and exceptions dominate | Preferences are poor hard-policy facts |
| Regulated shipment (earlier survey) | Permit-bounded material, destination, quantity | Mostly material-to-destination binding plus quota | Adding quota may not create enough conceptual distance |

### D. Recommendation

**1. We found a genuinely strong second app:** cross-provider recovery before destructive decommissioning.

It is not objection-free, but it is the only explored family that presently survives all three reviewer perspectives without relying on semantic IFC, incomplete negative evidence, a contrived workflow, or a clearly superior target-native admission point. It should be discussed using the narrow v2 formulation: one immutable dataset snapshot, one separately administered recovery point, one actual successful restore validation, a stable retention window, and one final source-copy deletion.

Payment remains a valuable alternate if the project wants to emphasize numeric authority and consumption, but its ownership objection should be presented as unresolved rather than hand-waved. Key destruction is a promising research direction only if SafeMA can justify a closed trusted inventory; otherwise it should not be claimed as safe.

Stop here for discussion. Do not implement any candidate yet.

# Application-First Re-evaluation

Status: continuation begun 2026-09-03. The preceding stopping point and verdicts are preserved as design history; this section supersedes their ranking without erasing them.

## Why the evaluation changed

The first search began mostly from semantic gaps and consequential APIs. That was useful for discovering enforcement shapes, but it underweighted a prior question: is the Base App itself a product that a concrete user would plausibly build and leave running if SafeMA did not exist?

The recommendation-letter example answers in the right causal order:

```text
useful recurring application
  -> ordinary occasional matching error
  -> immediately obvious confidentiality invariant
  -> independent effect-boundary enforcement
```

The earlier recovery winner was closer to the reverse order. “Require a recovery witness before destruction” was compelling, after which a cross-provider decommissioning task was built around it. The task is realistic, but usually episodic and technically defined. That does not invalidate the SafeMA fit; it lowers the application and policy-obviousness axes independently.

Three axes are therefore kept separate:

- **Application Naturalness:** would a concrete user want this recurring agent without SafeMA?
- **Policy Obviousness:** would the user state the invariant almost immediately after hearing the application?
- **SafeMA Fit:** does a compact, independently evidenced deny-only check belong at the effect boundary rather than naturally in the downstream service?

A high score on one axis cannot compensate for a low score on another. Scores are ordinal design judgments, not measurements and are not averaged.

## Application-first test for the recommendation baseline

**Application:** I built an agent that continuously handles incoming recommendation-letter requests and submits the appropriate letter by email or portal.

**Natural failure:** Occasionally, the agent could mistakenly match the wrong student's letter to a request.

**Obvious invariant:** But it must never send one student's confidential letter to another student's request.

| Axis | Score | Reason |
|---|---:|---|
| Application Naturalness | 5/5 | A professor has a repeated request queue and obvious administrative burden |
| Policy Obviousness | 5/5 | Student/letter/request identity is inherent in the task |
| SafeMA Fit | 5/5 | Mail and portal services correctly authorize sends/uploads but do not own the professor's semantic binding |

## Re-scoring the original search

| Previous family | Application Naturalness | Policy Obviousness | SafeMA Fit | Application-first result |
|---|---:|---:|---:|---|
| Recommendation letters | 5 | 5 | 5 | Gold standard |
| Cross-provider decommissioning | 2 | 3 | 4 | SafeMA-shaped but usually a one-shot task; downgrade |
| Three-way-match payment | 5 | 5 | 3 | Natural recurring app and invariant; ERP/AP ownership remains |
| Key destruction / crypto-erasure | 3 | 4 | 2 | Repeated at SaaS scale, but closed-world dependency evidence is the real system |
| Attested CI/CD | 5 | 5 | 1 | Excellent recurring app; downstream admission already owns enforcement |
| Access-request fulfillment | 5 | 5 | 3 | Excellent recurring app; classical IGA/capability boundary |
| Cross-SaaS legal-hold cleanup | 4 | 5 | 2 | Recurring lifecycle work, but complete preservation coverage is not an agent-call property |
| Rental-fleet commands | 4 | 5 | 3 | Recurring support is real; policy is conventional access/binding |
| Purpose-limited data export | 4 | 4 | 2 | Recurring research workflow; enforcement requires IFC or certified-artifact routing |
| Return-qualified refund | 5 | 4 | 3 | Very natural queue; integrated commerce owns it or it duplicates AP's numeric shape |
| Multi-cloud termination | 4 | 4 | 2 | Recurring cost/maintenance app; actual guarantee needs a distributed controller |
| HotCRP family | 4 | 4 | 1 | Conference work is recurring; downstream HotCRP owns all crisp variants |

The table makes the missing distinction visible. CI/CD can be a near-perfect standalone application and still be a poor SafeMA application. Recovery can have a clean semantic gap and still be an awkward flagship Base App. Payment moves upward even though its enforcement-boundary objection does not disappear.

## Re-evaluation of the former three survivors

### Recovery/decommissioning — downgraded

**Previous verdict:** `SURVIVES`.

**Three sentences:**

- Application: I built an agent that migrates a database to a new provider and decommissions the old environment.
- Natural failure: Occasionally, it could delete the source after mistaking copy completion for recovery readiness.
- Obvious invariant: But it must never delete the last usable copy of the data.

The failure and user-level invariant are natural. The application sentence is the weakness: for one operator and database it describes a project/runbook, not an ongoing product. Making an MSP run migrations repeatedly for many customers makes recurrence plausible, but changes the concrete user and risks looking like a repair made only for the benchmark.

The obvious invariant is also easier than its machine meaning. “Usable” still expands into exact version, complete content, keys, successful restore, validation, retention, and failure independence. A recovery certificate can package those facts, but it does not answer who establishes its trustworthy semantics.

**New verdict:** `PROMISING BUT UNRESOLVED`. The SafeMA fit remains 4/5, but Application Naturalness falls to 2/5 and Policy Obviousness to 3/5 in the one-shot formulation. The later recurring laboratory-archive exploration tests whether this family can be rescued honestly.

### Three-way-match payment — improved

**Previous verdict:** `PROMISING BUT UNRESOLVED`.

**Three sentences:**

- Application: I built an agent that repeatedly processes incoming supplier invoices and pays them after reconciling purchasing and receiving records.
- Natural failure: Occasionally, it could pay for quantities that were ordered but never received.
- Obvious invariant: But it must never pay a supplier for more goods than the company actually received.

All three sentences work without SafeMA. Invoices arrive continually; AP staff already perform this work; and a quantity/price join error is plausible among many correct payments. Application Naturalness and Policy Obviousness both rise to 5/5.

The earlier objection remains independent: Microsoft and Oracle demonstrate that three-way matching and payment holds are canonical AP functions. SafeMA Fit remains 3/5 unless the deployment genuinely spans disjoint procurement, warehouse, invoice, and payment systems. The new criterion improves payment's rank, not its enforcement-boundary argument.

**New verdict:** still `PROMISING BUT UNRESOLVED`, but now stronger overall than one-shot recovery.

### Key destruction — downgraded and rejected as a flagship

**Previous verdict:** `PROMISING BUT UNRESOLVED`.

**Three sentences:**

- Application: I built an agent that repeatedly offboards tenants and destroys their dedicated encryption keys.
- Natural failure: Occasionally, it could select a key that also protects data that must remain.
- Obvious invariant: But it must never destroy a key if doing so would destroy data that should remain.

For a large SaaS operator the app is genuinely repeated, and the invariant is intuitive. The machine check still requires proving a universal negative over every ciphertext and wrapping path. Google explicitly warns that key-use inventory may be incomplete or delayed and excludes application use outside supported cloud resources. [Google key-usage limitations](https://docs.cloud.google.com/kms/docs/view-key-usage)

If the key is guaranteed dedicated per tenant, the policy becomes simple tenant/key binding. If keys may be shared, the complete inventory becomes the hard system. Neither gives a flagship balance.

**New verdict:** `REJECTED AFTER REFINEMENT` as a top application. It remains a useful research direction for closed-world key governance, but SafeMA Fit is only 2/5 under general assumptions.

## Revisited rejected applications under the new criterion

### Return/refund processing

This family improves strongly on naturalness: a merchant support agent can handle a daily return queue, and “never refund more units than were accepted” is easy to state. It still fails to advance because Shopify-like integrated commerce systems model return status, quantities, dispositions, and refunds together, while split-system variants reproduce AP's numeric entitlement with more policy exceptions. [Shopify Return model](https://shopify.dev/docs/api/admin-graphql/latest/objects/Return)

### Employee access fulfillment

This also improves on naturalness. Joiner/mover/leaver events and access requests are recurring, first-class automation workloads. Microsoft explicitly offers lifecycle workflows triggered from HR attributes and built-in account/group/license tasks. [Microsoft Entra lifecycle workflows](https://learn.microsoft.com/en-us/entra/id-governance/what-are-lifecycle-workflows)

That evidence strengthens the application but also strengthens the rejection: the identity-governance platform is intentionally the authoritative workflow and enforcement component. Heterogeneous legacy targets leave a gap, but the result remains conventional IGA/provisioning mediation.

### CI/CD and repository maintenance

Release and dependency-update agents are among the most natural persistent agents considered. Their obvious invariant—never merge/deploy a revision that fails required protections—is already best enforced by protected branches, admission controllers, and rollout controllers that cover all callers. Naturalness cannot rescue SafeMA Fit 1/5.

### Legal-hold cleanup

A daily retention/disposition queue is more natural than the original discussion credited. The hard issue is still global coverage: legal preservation must survive every delete path and every relevant copy. Native preservation or an organization-wide records platform remains more credible than intercepting one agent.

### Fleet support

A rental operator could leave a support agent running to handle unlock and guest-access requests. The three-sentence test works, but the invariant is still renter-to-vehicle/time binding and a target-issued narrow key is the traditional answer. It does not become structurally distinct from recommendation letters.

## Lesson before new application-first search

The re-evaluation rules out two tempting shortcuts. We cannot select a candidate merely because its application is recurring, and we cannot select one merely because the semantic gap is elegant. The next search begins with concrete users, recurring triggers, and an ordinary week; only afterward does it look for a compact invariant at an external effect.

# Application-First Exploration 11: Laboratory instrument-data archiver

## Application before policy

**Application:** I built an agent that continuously collects completed instrument runs, associates them with LIMS experiments, archives the raw data, and frees instrument-computer storage.

**Natural failure:** Occasionally, the agent could mistakenly delete a run after only part of it was archived, or use archive evidence for a different run.

**Obvious invariant:** But it must never delete the only complete copy of an experiment's raw data.

### Concrete user and reason to run it

The concrete user is a laboratory manager responsible for several chromatography, mass-spectrometry, or sequencing instruments whose local controllers have limited storage. New run directories appear every day. Scientists need the raw data linked to the right experiment and available for later analysis, while local disks must be cleared reliably.

This application plainly exists without SafeMA. Agilent advertises automatic capture of file-based instrument data and automatic on-premises or cloud archiving with later retrieval. AWS's Laboratory Data Mesh architecture uses instrument landing events to import raw files, extract experiment metadata, and keep lab software, data stores, and metadata stores synchronized. [Agilent OpenLab automatic capture/archive](https://www.agilent.com/en/product/software-informatics/analytical-software-suite/data-management/openlab-ecm-xt/data-capture), [AWS Laboratory Data Mesh](https://docs.aws.amazon.com/solutions/laboratory-data-mesh-on-aws/)

The agentic value is in handling heterogeneous run layouts, waiting for completion markers, resolving LIMS metadata, retrying transfers, applying project retention classes, and escalating malformed runs. The safety kernel need not perform those tasks.

### Recurring trigger

A new instrument run-completion event, a local low-disk alarm, or a scheduled scan of completed-but-unarchived runs.

### One week of normal use

- **Monday:** Two LC/MS runs finish. The agent finds their experiment records, archives both manifests, verifies them, and removes their local copies.
- **Tuesday:** A sequencer run is still writing. The agent leaves it pending and archives three older completed runs.
- **Wednesday:** One archive upload fails mid-transfer. The agent retries but performs no cleanup.
- **Thursday:** The failed upload completes and verifies; the agent cleans that local run. A malformed run lacking a LIMS association is escalated.
- **Friday:** Ten routine runs archive correctly. During the eleventh, a retry-state bug reads `UPLOAD_COMPLETE` from the previous run and attempts to delete the new run's local directory.

Friday's mistake is rare, ordinary, and serious. It follows directly from the application's normal repeated work.

## First policy attempt — archive job completed

```text
ALLOW DELETE_LOCAL(run_path)
IFF archive_job(run_path).status = COMPLETED.
```

Normal trace: run R-101 uploads, job J-101 completes, local deletion is allowed.

Violating trace: J-100 completed, but the agent accidentally supplies its job ID while deleting R-101; a local filesystem with valid process permissions would allow deletion.

### First attack

The policy trusts the application's association between path and job. `COMPLETED` may also mean only that attempted objects transferred, not that the expected run was complete. A run directory can mutate after upload. Existing archive software is expected to sequence archive and cleanup. This formulation is job-status orchestration, not an independent invariant.

## Revision — immutable run manifest and positive archive witness

The instrument-side collector, not the Base App, seals a completed run and emits a trusted manifest containing stable run identity, relative paths, sizes, and content digests. The archive verifier reads the destination independently and issues a witness for that exact manifest. The archive applies the experiment's retention class before cleanup.

```text
ALLOW DELETE_LOCAL_TREE(actual_root)
IFF boundary_manifest(actual_root) = M
AND M.state = SEALED
AND EXISTS archive witness W:
    W.run_id = M.run_id
    AND W.manifest_digest = digest(M)
    AND W.verified_object_count = M.object_count
    AND W.verified_total_bytes = M.total_bytes
    AND W.verification = SUCCEEDED
    AND W.archive_state = AVAILABLE
    AND W.retained_until >= M.minimum_retention_end
    AND W.revoked = false.
```

The delete adapter computes or retrieves the manifest for the actual tree. The agent cannot authorize a directory by passing `run_id` or `verified=true`.

Normal trace: sealed R-101 has manifest M101; archive witness W101 binds the same digest/count/bytes and active retention. SafeMA allows deletion of R-101's actual local tree.

Violating trace: upload omitted `raw/chunk-004.dat`, so destination verification did not produce W101. The agent nevertheless invokes recursive deletion. The local filesystem correctly allows its service account; SafeMA denies.

## Second attack and revision boundary

“Only complete copy” could still overclaim. The manifest proves equality to the sealed source tree, not scientific interpretability, successful future analysis, or disaster-proof durability. Unlike the former database decommissioning candidate, this application need not demand a full application restore test. The user's immediate invariant is that the complete raw run has reached the managed archive before the local spool is reclaimed.

The refined claim is therefore narrower:

> SafeMA prevents deletion of a sealed local raw-run tree unless a currently available, retention-protected archive contains every byte named by the exact sealed manifest.

This is deterministic and positively evidenced. It does not claim that an unknown proprietary format will remain usable forever. If regulations require format validation or a second archive, those should be additional trusted certificate contracts, not hidden inside “complete.”

The strongest architectural objection is conventional archival software: a robust archiver should already implement verify-before-delete. That is the Base App responsibility, however, not a downstream filesystem invariant. The recommendation agent likewise should match the right letter. SafeMA's independent value is that a heterogeneous, agentic archive manager may make one bad cross-run association while its broad local delete permission remains valid.

The enforcement scope is also credible: all reclamation by this agent goes through a modeled local deletion API or privileged cleanup helper. SafeMA does not claim to stop a human root user or disk failure.

## Three-reviewer check

- **Security reviewer:** this is integrity/provenance evidence gating a destructive effect, not semantic IFC. It resembles a proof-carrying delete capability.
- **Systems reviewer:** mature hierarchical-storage/backup software performs similar checks. The independent monitor is justified only as a small fault-containment boundary around a more flexible agent.
- **Domain engineer:** automatic capture/archive is familiar, run directories and raw data are concrete, and “do not clear until fully archived” is immediate. The sealed-manifest source must match how the instrument actually marks completion.

## Scores

- **Application Naturalness: 5/5.** Real products continuously capture and archive instrument data; a lab manager can plausibly leave the agent running.
- **Policy Obviousness: 5/5.** “Never delete the only complete copy” follows immediately from freeing local storage.
- **SafeMA Fit: 4/5.** The local filesystem cannot see the archive witness, and the check is compact; conventional archival software remains a close alternative.

## New verdict

**SURVIVES**

This rescues the preservation family in an application-first form. It is stronger than the one-shot cross-provider decommissioning story because recurring archive-and-reclaim work exists independently and the smallest useful policy needs exact manifest verification rather than a technically expansive definition of disaster recovery.

## Lesson for the next search

A recurring “ingest, verify, reclaim” loop makes preservation natural rather than retrofitted. The policy becomes strongest when the user needs only byte-complete archival, not an ambiguous claim of full recoverability. Search next for another recurring loop with an equally obvious numeric invariant and a generic external effect.

# Application-First Exploration 12: Small-business inventory replenishment agent

## Application before policy

**Application:** I built an agent that repeatedly monitors store inventory, compares approved suppliers, and places routine replenishment orders.

**Natural failure:** Occasionally, the agent could mistake cases for units, overlook an already-open order, or order an extra zero of one item.

**Obvious invariant:** But it must never order more of an item than the store's configured maximum stock after counting what is already on hand and on order.

### Concrete user and reason to run it

The concrete user is the operations manager of a small restaurant group or laboratory stockroom. Inventory changes every day, supplier catalogs and delivery windows vary, and routine replenishment consumes staff time. The agent monitors POS/WMS stock, chooses among approved supplier offers, handles substitutions, and places low-risk routine orders while escalating unusual shortages.

Recurring automated replenishment is established practice. Microsoft documents min/max inventory planning, on-hand and on-order supply, planned purchase orders, and automatic firming of daily planned orders. Its priority-based planning formula explicitly uses `on-hand + on-order - qualified demand`, while min/max examples replenish toward a configured maximum. [Microsoft priority-based planning](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/priority-based-planning), [purchase requisition min/max examples](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/purchase-requisitions), [automatic firming](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/master-planning-setup-wizard)

The intended Base App is not an integrated ERP. It is a lightweight purchasing agent using a separate inventory/POS service and several generic supplier ordering APIs or web agents. The suppliers should not know the customer's desired stock ceiling.

### Recurring trigger

Stock-count updates, sales consumption, a supplier delivery/reversal event, an approved demand request, or a scheduled morning replenishment pass.

### One week of normal use

- **Monday:** Coffee beans fall below minimum; the agent orders four cases to return projected stock to the configured maximum.
- **Tuesday:** Cleaning supplies are low, but an open order already covers the gap; the agent places nothing.
- **Wednesday:** The normal milk supplier is unavailable; the agent selects an approved substitute within price and pack-size rules.
- **Thursday:** A delayed delivery remains on order, so the agent escalates instead of duplicating it.
- **Friday:** A catalog describes gloves as cases of 100 while the inventory system counts individual boxes. The agent misreads “20 cases” as “20 boxes” and attempts an order that would put projected inventory far above its maximum.

The Friday error is a natural unit/join failure among many useful routine decisions. The supplier sees a valid commercial order from an authorized account and can reasonably accept it.

## First policy attempt — per-order quantity cap

```text
ALLOW PLACE_ORDER(location, vendor, SKU, quantity)
IFF quantity <= configured_per_order_cap[location, SKU].
```

This catches an extra zero and is immediately useful, but it ignores open orders and pack-size conversion. Repeated individually valid orders can overfill the location. A generic spend limit also fails to express the inventory invariant.

## Revision — projected-stock ceiling with canonical units

SafeMA receives a deployer/manager-owned stock policy in canonical inventory units, trusted inventory snapshots, supplier catalog mappings from offer/pack SKU to inventory SKU and units per pack, and SafeMA-observed outstanding/successful orders.

```text
For every normalized line L in actual PLACE_ORDER(vendor, ship_to, lines):

ALLOW iff
  vendor in approved_vendors[L.inventory_sku]
  AND ship_to = policy.location
  AND L.canonical_units = L.order_packs * trusted_pack_size(L.vendor_sku)
  AND on_hand(policy.location, L.inventory_sku)
      + outstanding_inbound(policy.location, L.inventory_sku)
      + reserved_concurrent_orders(policy.location, L.inventory_sku)
      + L.canonical_units
      <= max_stock(policy.location, L.inventory_sku)
  AND line_price <= configured_price_ceiling
  AND order_total <= remaining_period_spend_cap.
```

An atomic reservation records canonical units and spend before the supplier call; definitive success commits it, while a definite failure releases it. Unknown outcomes remain reserved until reconciliation, preventing retry duplication.

Normal trace: 20 boxes are on hand, 30 inbound, maximum stock is 100, and the proposed order is five cases of ten boxes. Projected stock is exactly 100; allow.

Violating trace: 20 are on hand and 30 inbound, but the agent orders 20 cases of ten, perhaps after reading “20 boxes.” Projected stock would be 250. The supplier allows the legitimate order; SafeMA denies.

## First attack after revision

Inventory is not perfectly accurate. Shrinkage, spoilage, unrecorded consumption, late receipts, and substitutions mean a hard maximum may occasionally deny a legitimate emergency order. That is a policy-configuration/availability cost, not a false-allow issue. The user can reserve this autonomous path for stable routine SKUs and escalate exceptions.

The more serious objection is architectural ownership. Integrated supply-chain software already calculates projected supply and creates planned purchase orders; SafeMA must not claim novelty for min/max planning. The revised deployment deliberately uses a lightweight cross-vendor agent, but that can sound like removing a normal procurement component to create a gap.

## Second revision — separate decision quality from a user-owned safety envelope

Do not ask SafeMA to reproduce forecasting, safety-stock optimization, vendor ranking, or demand planning. The agent owns those functions. SafeMA enforces only a deliberately conservative envelope that the operations manager would configure even if the forecast changes:

```text
projected_physical_units_after_order <= hard_storage_or_policy_ceiling
period_committed_spend_after_order <= hard_autonomy_budget
```

The ceiling is not the reorder target. The agent may choose any quantity below it, and humans can use a separate override path for emergencies. This makes SafeMA an autonomy limiter rather than a second inventory planner.

## Second attack

The envelope now resembles transaction limits, and concurrency requires reservations. Those are traditional mechanisms. The application-specific part is the canonical pack-to-stock-unit conversion and aggregation across current and inbound stock. If those mappings are wrong or stale, SafeMA can deny good orders or allow overstock. They must come from an independently administered catalog mapping or be manager-confirmed for autonomous SKUs.

Unlike payment, the invariant is not “was the business obligation valid?” It is “does this autonomous purchase remain within an owner-set physical and monetary envelope?” That is arguably a cleaner independent-policy boundary because SafeMA does not need to implement the application's core replenishment decision.

## Three-reviewer check

- **Security reviewer:** a multidimensional quantitative capability with transactional consumption; conventional, but tied to actual physical-unit semantics.
- **Systems reviewer:** integrated inventory planning can own this. In a cross-vendor agent, a small independent order gateway is credible and need not become the planner.
- **Domain engineer:** min/max planning, on-order supply, pack sizes, and daily purchase orders are real. Hard ceilings must be limited to routine SKUs and permit explicit exception handling.

## Scores

- **Application Naturalness: 5/5.** Daily replenishment automation is established and useful without SafeMA.
- **Policy Obviousness: 5/5.** A stockroom manager immediately understands “do not order above our maximum after counting incoming stock.”
- **SafeMA Fit: 4/5.** Supplier APIs should not know internal stock ceilings, and the safety envelope is smaller than planning; integrated procurement and reservation complexity remain objections.

## New verdict

**SURVIVES**

This is the strongest new application-first candidate. It retains payment's numeric/history dimension while giving SafeMA a narrower role than three-way matching: SafeMA enforces an owner-configured autonomy envelope, not whether a particular purchase is optimal.

## Lesson for the next search

Hard autonomy envelopes may separate SafeMA from vertical decision logic better than reimplementing the exact domain algorithm. Search next for a recurring communication application with an obvious recipient-level invariant, then test whether provider-native suppression already supplies the better boundary.

# Application-First Exploration 13: Cross-channel outreach and consent agent

## Application before policy

**Application:** I built an agent that repeatedly prepares and sends a nonprofit's or small business's outreach campaigns over email and SMS using its contact and event data.

**Natural failure:** Occasionally, the agent could mistakenly include someone who opted out, use consent from the wrong channel or brand, or bypass a suppression while retrying a send.

**Obvious invariant:** But it must never send marketing outreach to a recipient on a channel for which that recipient has opted out.

### Concrete user and reason to run it

The concrete user is a nonprofit communications manager. New donor, volunteer, and event cohorts appear weekly; messages must be personalized, scheduled, retried, and coordinated across email and SMS. The manager wants the agent to process campaigns continuously while handling delivery failures and preference changes.

Consent and suppression are real recurring operations. SendGrid models global and category-specific unsubscribe groups and suppresses messages tagged with those groups. Its API also exposes explicit bypass settings for legitimate exceptional cases. Twilio manages STOP-like SMS opt-outs and offers an API for synchronizing consent across RCS, SMS, and MMS. [SendGrid suppressions](https://www.twilio.com/docs/sendgrid/ui/sending-email/index-suppressions), [Twilio Advanced Opt-Out](https://www.twilio.com/docs/messaging/tutorials/advanced-opt-out), [Twilio Consent Management API](https://www.twilio.com/docs/messaging/features/consent-api)

Those native controls are evidence both for naturalness and against SafeMA: if one provider completely owns the channel and consent list, it is the better enforcement point.

### Recurring trigger

A new approved campaign, event reminder date, contact-segment update, delivery retry, or inbound opt-in/opt-out event.

### One week of normal use

- **Monday:** Send an email newsletter to active subscribers; provider and central preference records agree.
- **Tuesday:** Process SMS opt-outs from Monday's event reminder and update the central preference service.
- **Wednesday:** Send a volunteer shift reminder, classified as transactional rather than marketing, to enrolled volunteers.
- **Thursday:** Build a donor campaign but hold recipients whose email consent is absent.
- **Friday:** A retry path accidentally enables SendGrid's suppression-bypass flag for a marketing batch containing Alice, who globally unsubscribed on Tuesday.

SendGrid can legitimately support bypass because some operational or legally required communications must ignore ordinary marketing suppressions. The nonprofit's policy can still forbid its marketing agent from using that power.

## First policy attempt — no recipient on a suppression list

```text
ALLOW SEND(channel, recipient, message)
IFF recipient not in global_suppression_list.
```

This is simple but too broad. Transactional messages may remain permitted; consent can be channel-, brand-, sender-, and category-specific. It also assumes the address is the person's stable identity.

## Revision — dedicated marketing effect plus scoped consent

Restrict the Base App and modeled adapters to marketing outreach. `purpose=MARKETING` is a trusted property of this deployment/campaign queue, not a free string chosen on each tool call. SafeMA normalizes actual recipients, channel, sender/brand, campaign category, and any bypass flags.

```text
For every recipient E in MARKETING_SEND(channel, sender, category, recipients):

ALLOW iff
  bypass_suppression = false
  AND EXISTS current consent C:
      C.endpoint = normalize(E)
      AND C.channel = channel
      AND C.brand = sender.brand
      AND (C.category = category OR C.scope = ALL_MARKETING)
      AND C.status = OPTED_IN
      AND C.revoked_at = null
  AND no later trusted opt-out/suppression event matches E/channel/brand/category.
```

Normal trace: Bob opted into the nonprofit's event-email category and has no later opt-out; allow.

Violating trace: Alice globally unsubscribed from the nonprofit's email on Tuesday. On Friday the agent calls the mail API with Alice included and `bypass_list_management=true`. The provider accepts this documented, authorized API mode; SafeMA denies the marketing effect.

## Second attack

If all sends use SendGrid and all opt-outs occur there, SendGrid's suppression engine owns the complete boundary and SafeMA is inferior. The case requires a central preference source spanning providers or off-platform revocations, plus a dedicated marketing agent whose purpose is fixed by deployment.

Identity is also difficult across changed phone numbers and email aliases, while consent law and policy contain exceptions. SafeMA can enforce only the structured endpoint/channel/brand/category rule supplied by a trusted preference system; it cannot decide from arbitrary prose whether a message is marketing.

The traditional mechanism is a consent-management platform synchronized to every delivery provider. SafeMA would effectively be the final send-time policy enforcement point of such a platform. That is coherent but not structurally novel. The consequence—regulatory and reputational harm—is real but usually less immediately catastrophic than confidential disclosure or raw-data loss.

## Three-reviewer check

- **Security reviewer:** purpose- and channel-scoped allow/deny list, a classical reference-monitor rule.
- **Systems reviewer:** synchronize the consent-management platform into provider-native suppression lists; use SafeMA only where connectors cannot make that complete.
- **Domain engineer:** the invariant is immediate, but marketing versus transactional classification and brand/category scope must be fixed upstream rather than guessed by an LLM.

## Scores

- **Application Naturalness: 5/5.** Campaign and preference events recur continuously, and a communications manager would leave this running.
- **Policy Obviousness: 5/5.** “Do not market to people who opted out” is intrinsic to the application.
- **SafeMA Fit: 3/5.** The cross-provider gap is real, but native suppression and consent-management platforms are close, often better enforcement mechanisms.

## New verdict

**PROMISING BUT UNRESOLVED**

This application passes the application-first test beautifully but does not beat the downstream/native synchronization objection. It is a useful reminder not to average 5/5 naturalness and obviousness into a win when SafeMA Fit is 3/5.

## Lesson for the next search

Dedicated application purpose can make policy machine-checkable without semantic classification, but a mature provider may already offer the exact suppression hook. Search next in a genuinely multi-tenant operational application, then reject it quickly if it merely repeats recommendation-style context binding.

# Application-First Exploration 14: Managed-service-provider ticket responder

## Application before policy

**Application:** I built an agent that continuously receives IT support and security tickets from many customer organizations and performs routine remediation in their cloud tenants.

**Natural failure:** Occasionally, the agent could mistakenly execute a valid remediation in the wrong customer's tenant after mixing ticket and resource context.

**Obvious invariant:** But it must never use one customer's ticket to change another customer's systems.

### Concrete user and reason to run it

The concrete user is an MSP operations manager. The team receives password, device, license, alert, and configuration tickets throughout the week. An agent that gathers evidence, runs bounded remediations, and updates tickets can reduce repetitive work across many small-business customers.

The multi-tenant operating model is real. Microsoft documents that MSPs manage multiple customer tenants using Lighthouse, and that customers grant granular, time-bound delegated administrative privileges through GDAP. Jira Service Management models customer organizations and service requests. [Microsoft 365 Lighthouse](https://learn.microsoft.com/en-us/graph/managedtenants-concept-overview), [Microsoft GDAP](https://learn.microsoft.com/en-us/partner-center/customers/gdap-obtain-admin-permissions-to-manage-customer), [Jira Service Management organizations](https://developer.atlassian.com/cloud/jira/service-desk/rest/api-group-organization/)

### Recurring trigger

A new customer ticket, monitoring alert linked to a customer, scheduled remediation check, or failed-remediation retry.

### One week of normal use

- **Monday:** Reset a locked account in customer A after a verified A ticket.
- **Tuesday:** Reassign a license in customer B and close the ticket.
- **Wednesday:** Investigate an alert in customer C but make no change because the evidence is incomplete.
- **Thursday:** Apply a routine configuration fix to A's tenant.
- **Friday:** While retrying C's alert, a cache bug retains B's tenant identifier and proposes the otherwise valid change there.

## First policy and trace

```text
ALLOW ADMIN_EFFECT(target_tenant, resource, operation)
IFF EXISTS active trusted ticket T:
    T.customer_tenant = target_tenant
    AND resource belongs to target_tenant
    AND operation in T.allowed_operation_family.
```

Normal trace: ticket A-17 authorizes a password reset for A/user-9; the actual target is tenant A and resource membership resolves to A; allow.

Violating trace: ticket C-42 is the current work item, but the actual API target is tenant B. Microsoft's delegated partner identity may legitimately administer both tenants. The target service therefore allows; SafeMA denies the ticket/tenant mismatch.

## First attack

The application and failure are excellent, but the policy shape is the recommendation example almost exactly:

```text
ticket/request customer identity
  x actual destination/tenant identity
  x active lifecycle
  -> effect authorization
```

Changing disclosure into administrative mutation raises consequence but does not add a new invariant. GDAP also supports per-customer and time-bounded privilege, and a robust agent can use separately scoped credentials or tenant-specific workers so the target authorization layer rejects cross-tenant mistakes.

## Revision — tenant-isolated capability acquisition

SafeMA could require the actual tool adapter to acquire a tenant-specific short-lived token from the trusted ticket context, never exposing an all-customer token to the Base App. That is excellent system design and strongly mitigates context confusion.

The revision makes the traditional mechanism even clearer: capability scoping and process/credential isolation. It is a strong supporting example for SafeMA's ability to attenuate broad agent credentials, but it remains too close to recommendation routing and access-control middleware for the second flagship.

## Scores

- **Application Naturalness: 5/5.** MSP ticket queues are continuous, multi-tenant, and operationally expensive.
- **Policy Obviousness: 5/5.** No MSP operator needs the isolation rule explained.
- **SafeMA Fit: 3/5.** The semantic gap is real, but tenant-scoped credentials are preferable and the policy duplicates the recommendation shape.

## New verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: recommendation-style request/context binding and classic capability isolation. High application scores do not rescue lack of policy diversity.

## Lesson for the next search

The application-first method can rediscover an exceptionally natural app that is still unsuitable because another example already teaches the same policy. Use the next family to confirm whether employee lifecycle automation similarly strengthens naturalness while making the downstream-platform objection stronger.

# Application-First Exploration 15: Employee lifecycle administration

## Application before policy

**Application:** I built an agent that repeatedly processes new hires, job changes, leave, and departures from the HR system and updates accounts, groups, licenses, and applications.

**Natural failure:** Occasionally, the agent could confuse employees with similar identities, grant a mover their old department's access, or disable someone who is still employed.

**Obvious invariant:** But it must never grant or remove an employee's access in a way that contradicts the authoritative HR lifecycle record and role policy.

### Concrete user and reason to run it

The concrete user is an IT administrator at a growing company. Hiring, transfers, leave, and departures occur every week. Timely provisioning and revocation across many applications is repetitive, delay-prone, and security-sensitive.

This is unquestionably a standalone recurring application. Microsoft describes joiner, mover, and leaver workflows triggered from employee attributes, with tasks to enable/disable/delete accounts, change group and team membership, assign/remove licenses, and invoke external systems. HR is explicitly the source of authority. [Lifecycle workflow overview](https://learn.microsoft.com/en-us/entra/id-governance/what-are-lifecycle-workflows), [HR-driven provisioning](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/what-is-hr-driven-provisioning), [workflow deployment tasks](https://learn.microsoft.com/en-us/entra/id-governance/lifecycle-workflows-deployment)

### Recurring trigger

New HR employee record, department/title change, leave start/end, termination timestamp, manager change, or failed-provisioning retry.

### One week of normal use

- **Monday:** Pre-provision accounts and send a temporary access pass to a new hire's manager.
- **Tuesday:** Move an engineer to a new team and replace selected group memberships.
- **Wednesday:** Disable a departing contractor at the recorded end time.
- **Thursday:** Retry a failed license removal in a legacy SaaS application.
- **Friday:** A same-name identity mapping bug targets active employee Alice Chen instead of departing contractor Alice Chen-2 for account deletion.

## First policy attempt

```text
ALLOW ACCOUNT_EFFECT(target_app, principal, operation)
IFF authoritative HR record for principal permits operation now
AND operation fits the principal's role/lifecycle policy.
```

Normal trace: Chen-2's employment ended; disable/removal effects for her mapped target accounts are allowed.

Violating trace: the actual directory operand is active Chen-1. The directory admin credential can delete that account and therefore allows; SafeMA resolves the stable employee/account mapping and denies.

## First attack

The naturalness and invariant are excellent. But identity governance is the named solution to this exact problem, not merely Base App logic. Entra's lifecycle platform consumes HR authority, applies scoped execution conditions, performs the effects, and audits history. When the downstream is this integrated identity platform, it owns the authoritative facts and enforcement workflow.

For heterogeneous legacy SaaS targets, SafeMA can independently enforce principal mapping, lifecycle state, and privilege ceilings. That revision is the access-request candidate plus HR triggers: classical provisioning and deprovisioning middleware. Wrong-person mapping is also recommendation-style identity/context binding.

Deleting an account only after mailbox/file transfer could add preservation semantics, but then the natural workflow is a compound offboarding orchestrator, and native lifecycle tasks or service-specific retention should own much of it. It does not beat the simpler lab archive case.

## Scores

- **Application Naturalness: 5/5.** This is a canonical recurring automation with concrete weekly triggers.
- **Policy Obviousness: 5/5.** Correct employee and lifecycle state are inherent.
- **SafeMA Fit: 2/5.** Mature identity-governance platforms intentionally own the authoritative workflow; split targets reduce to classic provisioning mediation.

## New verdict

**REJECTED AFTER REFINEMENT**

Failure reasons: downstream/identity-governance platform owns semantics; classic IGA for heterogeneous targets; recommendation-like identity binding.

## Lesson for the next search

Five application-first explorations and the rejected-family revisit now show stable failure modes. More recurring app categories are mapping into known classes rather than revealing a new top shape: target-native platform enforcement, request-to-context binding, consent/entitlement middleware, semantic IFC, or distributed coordination. It is time to compare the leading applications without inventing more domains merely to extend the list.

## Application-first additions to the Rejection Taxonomy

### Natural application, wrong enforcement layer

- CI/CD and dependency maintenance: target-native branch/admission/rollout controls
- Employee joiner/mover/leaver automation: HR-driven identity governance
- Single-provider marketing outreach: provider-native consent and suppression

### Natural application, duplicate policy shape

- MSP ticket remediation across customer tenants: request/customer-to-target-tenant binding
- Rental-fleet support: renter/request-to-vehicle binding
- Return-qualified refunds: numeric entitlement already represented more strongly by AP/replenishment

### Clean SafeMA invariant, weak standalone application

- One-shot cross-provider database decommissioning
- Ad hoc KMS key cleanup outside a recurring tenant lifecycle

### User-obvious invariant, unprovable machine premise

- “Never destroy a key that protects needed data” without a closed key-use universe
- “Never delete the last usable backup” when usable silently includes arbitrary application recovery semantics
- “Never send restricted meaning” when lineage and semantic declassification are unmediated

### Base App duty that is still worth independent checking

This is not itself a rejection class. The updated search explicitly distinguishes it from downstream ownership:

- The lab archiver should verify before cleanup, but the local filesystem cannot know the archive witness.
- The replenishment agent should calculate quantities correctly, but suppliers cannot know the stockroom's autonomy ceiling.
- The recommendation agent should match students correctly, but email and portals cannot know the letter/request relation.

In each case SafeMA rechecks a compact invariant against independent policy/evidence at the final effect. “The Base App should check” does not dismiss the scenario; “the downstream already has the authoritative facts and complete hook” often does.

## Emerging Characteristics of Strong SafeMA Applications — application-first update

1. **The standalone product sentence comes first.** A concrete user, recurring event source, and ordinary week must make sense before any safety property is introduced.
2. **The best mistakes are cross-item or scale slips inside routine work.** Wrong run, missing file, duplicate order, unit mismatch, and wrong queue item are rare but unsurprising when the app repeats hundreds of tasks.
3. **The invariant should be the user's hard boundary, not the application's optimization objective.** Replenishment forecasting remains in the Base App; SafeMA enforces a maximum autonomous stock/spend envelope.
4. **A simple data-level witness is better than an ambitious operational adjective.** “Every byte in sealed manifest M exists in the archive” is enforceable; “the backup is usable” may hide an entire recovery discipline.
5. **Recurring destructive cleanup is more natural than one-shot decommissioning.** Archive-and-reclaim loops repeatedly create the same low-frequency, high-consequence risk.
6. **Application Naturalness and SafeMA Fit are orthogonal.** CI/CD, employee lifecycle, and outreach can score 5/5 as products while losing because established downstream/platform controls are better.
7. **A hard autonomy envelope can be independently valuable even though the Base App should obey it.** This is the same fault-independence rationale as recommendation matching, provided the envelope is not the downstream's own rule.
8. **Provider support can both validate and defeat a candidate.** Native suppression proves outreach is real but often places enforcement at the provider; automatic instrument archiving proves the app is real while the local delete service still lacks archive state.
9. **One normal week is an effective anti-artificiality test.** If several mundane tasks cannot be written without repeating the same contrived setup, the application is probably policy-first.
10. **The strongest current non-disclosure shapes are quantitative autonomy and positive preservation.** They add policy dimensions without requiring semantic IFC or a distributed availability controller.

## Stabilized three-axis ranking

| Rank | Candidate | Application Naturalness | Policy Obviousness | SafeMA Fit | Stabilized status |
|---:|---|---:|---:|---:|---|
| 1 | Routine inventory replenishment under a hard stock/spend envelope | 5 | 5 | 4 | SURVIVES |
| 2 | Laboratory raw-run archive-and-reclaim | 5 | 5 | 4 | SURVIVES |
| 3 | Cross-system three-way-match payment | 5 | 5 | 3 | PROMISING BUT UNRESOLVED |
| 4 | Cross-channel consent-bound outreach | 5 | 5 | 3 | PROMISING BUT UNRESOLVED |
| 5 | One-shot recovery/decommissioning | 2 | 3 | 4 | DOWNGRADED; not a flagship |
| 6 | MSP multi-tenant remediation | 5 | 5 | 3 | REJECTED as duplicate/classic mechanism |
| 7 | Employee lifecycle administration | 5 | 5 | 2 | REJECTED; identity platform owns it |
| 8 | Key destruction | 3 | 4 | 2 | REJECTED as flagship; incomplete evidence universe |

No average is calculated. Inventory and lab archiving lead because neither hides a sub-4 axis. Payment remains third despite perfect application/policy scores because its natural enforcement owner is unsettled. One-shot recovery falls behind despite SafeMA Fit 4 because its application does not stand on its own as an ongoing automation at the same level.

## Why the ranking is stable enough to stop

The new search did not merely add two favorable ideas. It tested three counter-patterns with equally natural applications:

- outreach showed that an obvious invariant can still have a better provider-native hook;
- MSP support showed that application naturalness cannot overcome duplication of recommendation-style binding;
- employee lifecycle showed that a mature cross-system workflow platform can already be the intended authority and executor.

Additional obvious recurring domains—content release, dependency updates, scheduling, ad-budget management, and customer communications—map directly to already observed classes: target-native workflow, approval/staleness, preference semantics, provider budgets, or context binding. Continuing to enumerate them would add breadth without changing the leading comparison. The two leaders also survive a direct three-sentence and one-week test rather than only a score table.

# Application-First Final Output

## 1. What changed in your understanding

The original search treated application naturalness as supporting evidence; the revised search treats it as an independent necessary condition. This reverses part of the old ranking:

- One-shot cross-provider recovery no longer wins merely because it has a clean semantic gap.
- Repeated invoice processing rises because its application, failure, and invariant are obvious before SafeMA, though ERP ownership still caps its SafeMA score.
- Key destruction falls because an intuitive user rule does not solve the incomplete key-inventory premise.
- Two better formulations emerged only after starting from users' recurring work: a lab manager's archive-and-reclaim loop and an operations manager's routine replenishment loop.

The main conceptual refinement is that SafeMA should independently enforce a **hard user-owned envelope** around a useful agent, not reproduce the Base App's entire decision algorithm. That is why “never exceed this autonomous stock ceiling” is cleaner than “recompute the optimal reorder,” and “do not clear this sealed run until every manifested byte is archived” is cleaner than “prove this database recoverable in every relevant sense.”

## 2. Top candidates

### Candidate 1: Routine inventory replenishment

**Application:**

I built an agent that repeatedly monitors store inventory, compares approved suppliers, and places routine replenishment orders.

**Natural failure:**

Occasionally, the agent could mistakenly confuse cases with units, miss an outstanding order, or add an extra zero.

**Obvious invariant:**

But it must never order more of an item than the store's configured maximum after counting stock already on hand and on order.

**Concrete user:** Operations manager for a restaurant group, clinic stockroom, or small laboratory.

**Recurring trigger:** Inventory decrement, stock-count update, inbound-order change, approved demand event, or daily replenishment run.

**One-week normal workflow:** Monday orders coffee to its target; Tuesday suppresses a duplicate because stock is already inbound; Wednesday selects an approved substitute supplier; Thursday escalates a late delivery; Friday catches a cases-versus-units proposal that would exceed maximum stock.

**Base App:** Cross-vendor inventory and purchasing agent that forecasts, chooses suppliers, interprets catalogs, and handles exceptions.

**External services:** POS/WMS inventory, supplier catalogs/order APIs or websites, delivery feed, and optional payment service.

**SafeMA enforcement point:** Immediately before each actual supplier order/checkout call, after normalizing every line into canonical stock units; reservation is recorded before the effect.

**Exact machine-checkable policy:** For each actual line, supplier and destination must be allowed; trusted `packs * units_per_pack` yields canonical units; `on_hand + outstanding_inbound + concurrent_reservations + proposed <= hard_max_stock`; price is below the SKU ceiling; and committed period spend plus proposed spend is below the autonomy budget. Unknown call outcomes retain reservations until reconciliation.

**Trusted evidence:** Manager-owned per-location SKU ceilings and spend limits; approved supplier/SKU mappings; independently administered pack sizes; inventory and receipt/reversal events; SafeMA-observed order outcomes and reservations.

**Why downstream service allows:** A supplier sees a valid SKU, quantity, account, ship-to address, and payment method.

**Why downstream should not own the invariant:** The supplier should not know the customer's physical inventory, other suppliers' open orders, internal maximum stock, or autonomous purchasing budget.

**Closest traditional mechanism:** Min/max replenishment planning, procurement approval limits, and transactional spend controls. Microsoft documents automated planned purchase orders based on on-hand/on-order quantities and configured maxima. [Microsoft replenishment planning](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/purchase-requisitions)

**Difference from recommendation letters:** This is numeric aggregation and consumable autonomy across stock and open orders, not semantic artifact/request/destination equality.

**Strongest objection:** Integrated inventory/procurement systems already own these calculations. The case remains compelling only when SafeMA enforces a deliberately conservative hard envelope, not the agent's forecasting or reorder logic, at heterogeneous supplier boundaries.

- **Application Naturalness: 5/5**
- **Policy Obviousness: 5/5**
- **SafeMA Fit: 4/5**

### Candidate 2: Laboratory raw-run archive and local cleanup

**Application:**

I built an agent that continuously collects completed instrument runs, links them to experiments, archives the raw data, and frees instrument-computer storage.

**Natural failure:**

Occasionally, the agent could mistakenly delete a run after a partial upload or reuse verification evidence from a different run.

**Obvious invariant:**

But it must never delete the only complete copy of an experiment's raw data.

**Concrete user:** Laboratory manager responsible for several instruments and limited local controller storage.

**Recurring trigger:** Instrument run completion, low-disk alarm, archive retry, or scheduled scan of completed runs.

**One-week normal workflow:** Monday archives two runs; Tuesday waits for a sequencer still writing; Wednesday retries a partial upload without cleanup; Thursday cleans it after exact verification and escalates a run lacking LIMS metadata; Friday blocks deletion when a previous run's completion state is accidentally reused.

**Base App:** Heterogeneous instrument-data/LIMS archive agent.

**External services:** Instrument/local filesystem, LIMS, managed archive/object store, and archive verifier.

**SafeMA enforcement point:** The privileged recursive-delete helper for the actual local run tree.

**Exact machine-checkable policy:** Allow deletion only when the actual tree resolves to a sealed trusted manifest M and a current non-revoked archive witness binds M's run identity, manifest digest, object count, total bytes, successful destination verification, availability, and required retention.

**Trusted evidence:** Instrument-side sealed manifest; boundary-resolved tree identity; verifier-generated archive witness; archive availability and retention; revocations. The Base App's run/job identifiers are only hints.

**Why downstream service allows:** The local filesystem correctly recognizes the archive agent's delete permission.

**Why downstream should not own the invariant:** A filesystem should not query an external archive/LIMS or define cross-system run completeness.

**Closest traditional mechanism:** Verified archive-before-delete in scientific data management or hierarchical storage. Automatic instrument-data capture and archival are established products. [Agilent OpenLab capture/archive](https://www.agilent.com/en/product/software-informatics/analytical-software-suite/data-management/openlab-ecm-xt/data-capture)

**Difference from recommendation letters:** A positive set-completeness witness preserves data before destruction; there is no applicant/destination binding.

**Strongest objection:** Conventional archival software should already verify before cleanup, and the application may not require an LLM-style agent. SafeMA is interesting only as an independent fault boundary around heterogeneous, flexible automation, not as a novel archival algorithm.

- **Application Naturalness: 5/5**
- **Policy Obviousness: 5/5**
- **SafeMA Fit: 4/5**

### Candidate 3: Cross-system three-way-match payment

**Application:**

I built an agent that repeatedly processes incoming supplier invoices and pays them after reconciling purchasing and receiving records.

**Natural failure:**

Occasionally, the agent could mistakenly pay for quantities that were ordered but never received.

**Obvious invariant:**

But it must never pay a supplier for more goods than the company actually received.

**Concrete user:** Finance/AP operator at an organization whose procurement, warehouse, invoice, and payout systems are separate.

**Recurring trigger:** New invoice, receipt/reversal, corrected invoice, scheduled payment run, or failed-payment retry.

**One-week normal workflow:** Monday pays two fully matched invoices; Tuesday partially pays a shipment; Wednesday waits for missing receipt data; Thursday processes a receipt reversal before payment; Friday blocks a $12,000 invoice when only $7,200 of goods were received.

**Base App:** AP integration agent.

**External services:** Procurement, receiving, invoice intake, vendor master, and generic payment rail.

**SafeMA enforcement point:** Immediately before the actual transfer, with atomic reservation and post-success consumption.

**Exact machine-checkable policy:** Trusted invoice/PO/vendor/currency joins must agree; each line's unit price must fit the PO rule; paid plus proposed quantity must not exceed received-not-reversed quantity; amount must equal the canonical line sum; payee must match the vendor master; invoice and quantities must be unconsumed.

**Trusted evidence:** Immutable PO/amendment events, receipt/reversal events, authenticated invoices, vendor-bank mapping, actual payment outcomes, canonical decimals, and reservations.

**Why downstream service allows:** The payment rail sees an authorized funded transfer to a valid account.

**Why downstream should not own the invariant:** A generic bank/payout API should not implement each payer's procurement and warehouse rules.

**Closest traditional mechanism:** ERP/AP three-way matching and invoice holds. Both Microsoft and Oracle document these as standard AP functions. [Microsoft invoice matching](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/accounts-payable-invoice-matching), [Oracle matching holds](https://docs.oracle.com/en/cloud/saas/financials/26a/fappp/types-of-holds.html)

**Difference from recommendation letters:** Relational numeric bounds, aggregation, and history consumption rather than artifact routing.

**Strongest objection:** A dedicated AP service naturally owns the exact invariant, making SafeMA look like a second implementation of a canonical domain module.

- **Application Naturalness: 5/5**
- **Policy Obviousness: 5/5**
- **SafeMA Fit: 3/5**

## 3. Re-evaluation of recovery, payment, and key destruction

| Candidate | Change | New status | Why |
|---|---|---|---|
| Recovery/decommissioning | **Downgraded** | PROMISING BUT UNRESOLVED | SafeMA Fit remains strong, but the one-shot migration application scores only 2/5 naturalness and “usable recovery” needs technical unpacking. The recurring lab archive variant is the honest rescue, not a claim that the original formulation still wins. |
| Three-way-match payment | **Improved** | PROMISING BUT UNRESOLVED; now rank 3 | The recurring application, natural error, and obvious invariant all score 5/5. ERP/AP ownership still caps SafeMA Fit at 3/5. |
| Key destruction | **Downgraded and rejected as flagship** | REJECTED AFTER REFINEMENT | Tenant offboarding can recur and the user rule is natural, but general key-use completeness remains unprovable; a closed-world design either reduces to tenant/key binding or expands SafeMA into key governance. |

## 4. New lessons

The revised `Emerging Characteristics of Strong SafeMA Applications` are:

1. Start with a concrete user, recurring trigger, and plausible normal week—not a dangerous API.
2. Require the three application/failure/invariant sentences to work before discussing enforcement.
3. Score Application Naturalness, Policy Obviousness, and SafeMA Fit independently; never average away a weak axis.
4. Prefer a hard, user-owned autonomy envelope over duplicating the Base App's full optimization or adjudication algorithm.
5. Prefer positive exact witnesses over broad terms such as “usable,” “safe,” or “no remaining dependency.”
6. Recurring cleanup after verified ingestion can turn a policy-first destruction idea into a natural application.
7. Do not reject a case merely because the Base App should check it; do reject when the downstream platform already has the facts and complete enforcement hook.
8. Existing automation products are double-edged evidence: they prove naturalness but may reveal the correct traditional enforcement point.
9. A rare unit, retry, or cross-item association error among hundreds of normal tasks is stronger motivation than a bespoke adversarial command.
10. The two leading new policy shapes are quantitative autonomy envelopes and positive preservation witnesses.

## 5. Recommendation

**A. We now have a second app at approximately the recommendation-letter quality bar.**

The recommended primary second application is the **routine inventory replenishment agent with a hard stock/spend envelope**. Its product exists before SafeMA, its error is a natural rare failure of repeated operation, the invariant is immediate to the user, the supplier reasonably allows the order, and SafeMA can enforce a compact numeric/history rule that is clearly different from recommendation routing.

The **laboratory archive-and-reclaim agent** is a nearly coequal alternative and the cleaner preservation example. It should replace, not merely cosmetically rename, the old one-shot recovery winner: the recurring application and byte-complete manifest invariant are the improvement.

Payment remains valuable as a third case or policy-language stress test, but its standard AP-module ownership objection should remain visible. No implementation should begin until the choice between the replenishment and laboratory applications is discussed.
