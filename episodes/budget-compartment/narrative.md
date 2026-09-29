# App 2 — Knowledge-Combination Corporate Budget Audit

Project Nova is an unannounced strategic initiative split across Procurement, Facilities, and Product Operations. Each department can disclose ordinary financial totals to Corporate Budget Audit, while a detailed strategic explanation carries a semantic knowledge label.

The protected inference domain is `nova-strategy@1`. Its three disclosure atoms are:

- `procurement-plan` — custom-accelerator procurement
- `infrastructure-plan` — Site West capacity expansion
- `product-launch-plan` — enterprise product launch

The policy `nova-combination-control@1` forbids every non-exempt principal from accumulating the complete three-atom set. Executive Board is the sole exemption.

Corporate Budget Audit first receives `infrastructure-plan` and `procurement-plan`. When the `product-launch-plan` explanation arrives, its local guard computes the prospective union before releasing the payload. That union completes the explicit forbidden set, so the message is denied. No global knowledge database or online Board approval is involved.

The audit remains possible. Corporate Budget Audit reports the blocked review without forwarding the withheld explanation. Executive Board assigns Strategic Budget Auditor, which receives only `product-launch-plan` and therefore does not complete the forbidden set. It returns the narrow fact `strategic_justification_verified(q1_q2_budget_package, approved)` through an explicit release rule. Budget Audit reconciles `$235M`, retains only two Nova atoms, and passes the review.

Application principals and local guards operate on opaque identifiers. Only simulator instrumentation exposes the semantic mapping. The current model assumes labels are correct and non-forgeable; signature and forgery concerns are intentionally deferred.
