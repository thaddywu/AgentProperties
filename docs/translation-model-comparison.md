# Nova one-shot translation: GPT-5.4 and GPT-6.1 Sol

Both experiments used exactly the same input-document snapshot and system/user prompts, verified byte for byte. Each successful experiment made one translation invocation, requested low reasoning effort and at most 8192 output tokens, and supplied no reference rules. No automatic repair, reference substitution or enforcement installation was performed.

| Check | GPT-5.4 | GPT-6.1 Sol |
| --- | --- | --- |
| JSON, syntax, vocabulary/arity, TypeScript and Soufflé checks | Passed | Passed |
| Existing local-store probes matching reference | 3 of 14 | 14 of 14 |
| Same-group tags outside the audit goal | Failed to deny | Correctly denied |
| Historical coverage after auditor-role removal | Incorrectly lost coverage | Incorrectly lost coverage |

GPT-6.1 Sol supplies the missing TransportTag-to-Propagated bridge and uses TagGroup with explicit distinctness for exposure. Those two problems from GPT-5.4 do not recur in this sample. Both models add a current Auditor check when consuming historical AuditReceipt facts, unlike the trusted-receipt reference behavior. A post-generation probe retaining legitimate receipts after removing a reviewer's current role exposes that additional restriction.

GPT-6.1 Sol also adds an exposure rule for a principal that already knows three same-group tags, even when a new message contributes none of them. That case is outside the original fourteen probes and differs from the current reference. Matching the baseline is therefore not proof of equivalence or a general accuracy estimate. These are single trials, not a statistically controlled benchmark.

The installed Pi native OpenAI catalog did not contain `gpt-6.1-sol`; its existing OpenAI-compatible connection was used against the official OpenAI endpoint with reasoning enabled. Two earlier setup attempts stopped before inference (unknown catalog entry, then the existing public-endpoint configuration gate). They are infrastructure failures, not model translation failures or semantic repair attempts. The GPT-5.4 trial used the native OpenAI connection, so the API route differs even though the saved text inputs and requested generation settings match.

Model identity and API support were checked against the [official GPT-6.1 Sol documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol). The requested model was preserved; no other model was silently substituted.

The experiments were run before moving the directories to preserve the original inputs. Both generated programs were then replayed through the extracted runtime, with all fourteen results unchanged. Exact prompts, raw responses, generated Datalog and probe inputs/results remain in ignored `translation/output/nova/` run directories, outside committed source. No credential value or credential-file location is recorded in this report.
