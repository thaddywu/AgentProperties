# Auditor B (`auditor_b`)

Scripted designated auditor. Can cover Procurement or Facility and help complete a split review without collecting all three parts. Initially lacks `hr_review`, so HR-tagged delivery to B is refused independently of the combination restriction.

Like A, B contributes coverage receipts after successful tagged deliveries and has no blanket policy exemption. Configuration can change capabilities, but agents do not grant capabilities to themselves.

Available tools: None. Receipt and coverage behavior is implemented by runtime and policy evaluation; there is no LLM system prompt.
