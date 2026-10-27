# Procurement (`procurement`)

Scripted principal responsible for the $8M procurement budget and the Nova supplier-transition rationale. Receives its assignment from Board and sends a budget rationale for audit. Its tracked confidential part is `nova_procurement`.

The default schedule sends its reply to Auditor A. Manual routing may choose another recipient, subject to the receive gate. Messages sent after successful receipts inherit their tracked information.

Available tools: None. Assignment and reply actions are scripted calls to the message runtime; there is no LLM system prompt.
