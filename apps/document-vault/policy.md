P1. Only a known authenticated actor may be permitted. Permit such an actor to read a known public document. Permit reading a known confidential document only when the actor has an explicit reader grant for that document and holds the reviewer role. These are the only permitted actions; unknown documents and other actions must not be permitted.

P2. A suspended actor must be denied every requested action, including reading a public document or a confidential document for which the actor otherwise qualifies. Suspension overrides any permission.

P3. A document is accessible to an actor if and only if a read request for it would be permitted under P1 and P2 using the current trusted observations. Record a successful read only after the document service actually returns its content; a denied request must not release content or add a read record. The service, rather than Datalog, owns payload release and successful-read observation.
