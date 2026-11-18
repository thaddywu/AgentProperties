# Policy adder

`translate(source, binding, generate, ...)` produces a pinned review draft. It decomposes source requirements, generates shared rules and calls the independent rules-reading module. Compilation checks structure, schemas, ownership and stratification; it does not establish policy fidelity. Drafts never install themselves.

```python
from policyweave.policy_adder import translate

draft = translate(policy_text, binding, generate)
```

`policy-translate --help` operates on a policy and existing binding. `policyweave add --help` selects the optional source-inspect/edit/test coding-agent adapter. That adapter requires Docker and a standalone CLI; base imports require neither. Shared policy/schema facts come from `core`; reverse descriptions come from `back_translation`, source alignment from `policy_viewer`.

See [porting](../../../docs/porting.md), the
[EDB/translation design](../../../docs/design/observations-and-translation.md) and the
[port contract](porting-contract.md). The
[staged port workflow](../../../docs/design/port-pipeline.md) describes the
implemented host-owned discovery, binding, rules and instrumentation/verification
stages. `binding.py` validates source evidence and fixed schemas; `harness.py`
persists progression, freezes contracts/rules and checks native gate traces.
The binding freezes explicit role/group/grant/FSM configuration. PrincipalGroup
records direct roles or user groups; shared InGroup supplies nested membership.
Custom IDB starts empty. At most eight justified helpers may be planned for
negative existence, reused nontrivial joins, recursion or global violations;
rules cannot invent further predicate names. Simple aliases and unused helpers
are rejected. The final IDB set freezes with accepted rules; instrumentation
cannot change it. Helpers introduce no new input predicates or producers.
Inventory and binding use `CodexPort.plan()`: bounded provider-neutral model
calls with strict JSON schemas and a host-selected original-source bundle, no
file tools and no app execution. The coding CLI runs only the rules and
instrumentation stages. Host validation still checks evidence and contract
consistency after structured generation.
Planning errors can restrict repair to rejected top-level sections; the host
merges retained sections and revalidates the whole plan. Instrumentation checks
reject unchanged planned source symbols and require worker-collected
`nativeBoundaryCalls` for every planned boundary. This is scoped placement and
execution evidence, not proof of business success or complete mediation.
`CodexPort.translate` uses this harness and does not automatically invoke later
`backtranslate` or `review` entries. Structural checks and source references do
not prove every mapping's semantics, policy fidelity or complete mediation.
