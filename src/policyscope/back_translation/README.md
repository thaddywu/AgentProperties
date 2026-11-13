# Back-translation

This module independently describes the implemented policy layer. `rules.py` reads actual rules plus trusted meanings and gate configuration. `execution.py` additionally reads implementation evidence, validates citations and retains unresolved assumptions. `codex.py` supplies the isolated implementation-only reverse session for an injected coding-agent port.

```python
from policyscope.back_translation import describe_execution

procedures = describe_execution(rules, binding, evidence, generate)
```

`evidence` maps relative source names to their implementation text. Neither source policy nor a forward plan is an input to this API. The separate viewer alignment pass can subsequently relate frozen descriptions to original sentences.

`policy-backtranslate --help` reads a JSON implementation bundle with `rules`, `binding` and `evidence`. The CLI stores private attempts, descriptions and measured usage. Rule coverage and exact source citations are checked; semantic accuracy still requires review.
