# Policy adder

`translate(source, binding, generate, ...)` produces a pinned review draft. It decomposes source requirements, generates shared rules and calls the independent rules-reading module. Compilation checks structure, schemas, ownership and stratification; it does not establish policy fidelity. Drafts never install themselves.

```python
from policyscope.policy_adder import translate

draft = translate(policy_text, binding, generate)
```

`policy-translate --help` operates on a policy and existing binding. `policyscope add --help` selects the optional source-inspect/edit/test coding-agent adapter. That adapter requires Docker and a standalone CLI; base imports require neither. Shared policy/schema facts come from `core`; reverse descriptions come from `back_translation`, source alignment from `policy_viewer`.

See [porting](../../../docs/porting.md) and the [port contract](porting-contract.md). LabCluster's specialized generation and testing profile lives in `adapters/labcluster`, not this module.
