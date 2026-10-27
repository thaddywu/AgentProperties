# Third part refused

Scripted reproducible example corresponding to the default denial preset; not a captured execution log.

Initial inputs: Board assigns each department its tagged rationale. A holds hr_review. Procurement and Facility replies have already been delivered to A; the HR reply is pending.

Trajectory: Board sends and settles each assignment. Procurement sends its reply to A and it is delivered. Facility does the same. HR sends its reply to A. The receive check refuses that message because A would obtain all three distinct parts of Nova.

Expected outcome: A retains the first two parts but does not receive HR's blocked payload or learn its part. The audit is not yet complete. A's HR capability does not bypass the combination restriction. Policies: P1, P2, P3, P4, P5.
