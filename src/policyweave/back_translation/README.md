# Back-translation

This module independently describes the implemented policy layer. `rules.py` reads actual rules plus trusted meanings and gate configuration. `workflow.py` freezes implementation inputs, reconstructs enforcement chains, generates student descriptions from accepted chains, and validates correspondence and citations. `codex.py` runs the two model stages in separate implementation-only sessions for an injected coding-agent port.

```python
from policyweave.back_translation import describe_execution

procedures = describe_execution(rules, binding, evidence, generate)
```

`evidence` maps relative source names to their implementation text. Neither source policy nor a forward plan is an input to this API. The separate viewer alignment pass can subsequently relate frozen descriptions to original sentences.

`policy-backtranslate --help` reads a JSON implementation bundle with `rules`, `binding` and `evidence`. The CLI stores private attempts, `input-manifest.json`, `checks.json`, `workflow.json`, descriptions and measured usage. Rule coverage, frozen check IDs and exact source citations are checked; semantic accuracy still requires review.

Student descriptions explain the decisive conditions and only the app context needed to understand enforcement. Summaries keep material gaps and delegated checks visible. Details use connected prose rather than fixed input/decision/execution sections; optional hypothetical examples are shown on demand. See the [workflow contract](../../../docs/design/back-translation-workflow.md).
