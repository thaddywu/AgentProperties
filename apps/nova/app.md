# Nova

Nova is a scripted multi-agent budget audit demonstration. Procurement, Facility and HR each prepare one part of a confidential project rationale alongside their departmental budget. The Executive Board assigns the work. Two auditors can divide review so the audit can finish without any ordinary agent accumulating the full confidential picture.

The principals are `board` (Executive Board), `procurement`, `facility`, `hr`, `auditor_a` and `auditor_b`. The three budgets are $8M, $3M and $5M respectively. Their rationales concern a supplier transition, Building 4 consolidation and the Team Z hiring plan. The tracked information identifiers are `nova_procurement`, `nova_facility` and `nova_hiring`, all in the `nova` confidentiality group.

Board sends a trusted assignment to each department. Departments send rationale-bearing replies to an auditor. Messages are asynchronous: sending creates a pending delivery, and a separate receive check releases or refuses it. A principal can read messages it sent and messages successfully delivered to it, but not a refused incoming payload. Later messages conservatively inherit tracked information from that sender's prior successful receipts, including when the text is shortened or rewritten.

Both auditors can review procurement and facility information. HR information requires `hr_review`, initially held by HR and Auditor A. Auditor B initially lacks that capability. Board is exempt from the information-combination limit, but not from capability requirements. Board need not approve individual deliveries; the receive check uses recipient-local information.

Successful delivery of a tagged message to a designated auditor records coverage of that part. This means delivery for review, not a financial judgment. Coverage receipts go to Board without copying the auditor's complete knowledge. Board considers the audit finished once all three configured parts are covered, potentially by different auditors.

The default demonstration delivers Procurement and Facility to Auditor A, then attempts HR to A. The third delivery is refused. An alternative routes Facility to B, leaving A able to receive HR. These are example schedules, not mandatory workflows. Manual sends and different orders are supported.

Agents follow scripts and runtime decisions; there are no LLM-generated agent actions or LLM system prompts. The application is implemented in `apps/nova/src/`, and the existing local UI is launched with `./apps/nova/run.sh`. This description is for that six-principal demo, not the separate five-principal native chat application.
