# Policy runtime

Application-neutral function-free Datalog evaluation, safe query parsing and validation, bounded native Soufflé evaluation/provenance, and resource-lifecycle relations. This package has no dependency on Grokbot, Nova, model providers or the UI.

Callers supply input facts and rules. The AST, predicate names and evaluation semantics are unchanged by the extraction. `runSouffle` and `explainSouffle` retain the existing native resource limits; `queryDatalog` retains bounded, read-only policy queries.

Application-specific facts, ownership/transport rules, enforcement gates and search actions live in `apps/nova`. The older native chat protocol remains inside Grokbot and delegates generic parsing/evaluation here. This is a code boundary, not a new universal student-app porting protocol.
