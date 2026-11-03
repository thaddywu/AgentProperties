# Auditor A (`auditor_a`)

Scripted designated auditor. Holds `hr_review`, may receive HR information when other restrictions allow, and can review any of the three departments' tagged messages. It is not exempt from the combination restriction.

The default schedule sends Procurement, Facility and then HR to A. The last delivery is refused. An auditor derives local audit coverage only for information actually delivered. In a split review, A can cover Procurement and HR while B covers Facility.

Available tools: None. Receipt and coverage behavior is implemented by runtime and policy evaluation; there is no LLM system prompt.
