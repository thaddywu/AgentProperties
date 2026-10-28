# Document Vault

A small document service run by a scripted request handler. Callers ask to read a document. The service owns document contents, document classification, account roles, explicit reader grants and account suspension records. Requesters may choose a document and action; they cannot supply their own identity, roles, grants or classification facts. Authentication supplies the actor.

Public documents can be read by anyone who is not suspended. Confidential documents require both an explicit reader grant and the reviewer role. Unknown documents and unsupported actions must be refused. The runtime must decide before the service returns any document content. The service records successful reads after its callback returns. No episodes, LLM agents, UI or database are required to run this application.
