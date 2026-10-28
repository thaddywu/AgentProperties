# Application → translation → runtime

Verified on 2026-10-28 using the independent Document Vault application. This application imports the generic runtime SDK and does not import Nova or start Grokbot services.

The run used one GPT-6.1 Sol invocation through the existing model adapter, with low reasoning and an 8192-token output limit. The prompt contained the app Markdown and the adapter-owned vocabulary/runtime contract. It did not include reference rules or acceptance cases. No repair attempt or handwritten-rule fallback was used.

The model returned five Datalog rules for three policies. The shared TypeScript parser, schema/head validation, safety/stratification checks and eight predeclared allow/deny cases passed. Translation exported a bundle. The actual application then loaded that exact source, pinned its own binding, revalidated it and ran the document callback through the generic gate.

| Execution check | Observed result |
| --- | --- |
| Public document read | Allowed, returned body |
| Confidential read without grant/role | Refused, no callback or body |
| Confidential read with grant and reviewer role | Allowed, returned body |
| Public read by suspended actor | Refused, no callback or body |
| Business callback count | Two calls for four requests |
| Successful-read observations | Two records; no denied-read record |
| Query over `Accessible` | Returned the three expected actor/document pairs |
| Why for an accessible confidential document | Explained the role, grant, known actor and classification inputs |
| What-if adding a role/grant | Allowed hypothetically; actual state remained unauthorized |

The generated source is byte-for-byte identical to the source in the executed bundle. The bundle hash for this run is `0afda4151a0686b884a35e029674b08ac992608601a935d9e5e33d1bf0321192`. Raw inputs, response, generated rules, bundle, validation and execution results remain in the ignored `translation/output/document-vault/` run directory.

This establishes an executed integration path, not general translation correctness. In a post-generation probe, a document marked both Public and Confidential was refused: the model added `not Confidential` to public-read rules. That case was outside the eight acceptance cases. The generic runtime does not enforce mutually exclusive classifications, and the extra restriction needs semantic review if such input states are possible. The generated program was preserved unchanged.

The interface is an in-process TypeScript SDK. Application developers still provide trusted observations and wrap the actual business action. It does not automatically instrument arbitrary source code, authenticate callers, persist sessions, coordinate workers or roll back external effects. Query/proof access is for the trusted adapter to authorize. Generic prevention search and completion planning remain future work; Nova's domain-specific analyses keep their existing implementation.

[Reproduce the application run](../apps/document-vault/README.md) · [Runtime API](../runtime/README.md) · [Translation command](../translation/README.md)
