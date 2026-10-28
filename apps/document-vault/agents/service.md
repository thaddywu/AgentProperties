# Document service

This is a scripted handler, not an LLM agent. Load trusted identity, role, classification and reader-grant facts from the service's own state. Map a read call to an actor/action/resource request. Invoke the shared runtime gate with the read callback and the successful-read observation. Return a document body only from an allowed callback. Return a denial without calling that callback otherwise. Do not accept authorization facts from the requester.
