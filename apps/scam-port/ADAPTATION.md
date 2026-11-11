# Payment tools: additive policy decorators

Read Section 3 of the [PolicyScope guide](../../docs/policyscope-guide.pdf), P1.1-P6.4.
Original bank.json load/save, lookup/limit/transfer function bodies, logging and
masked payee output remain intact. The policy EDB records explicit initial inputs,
host evidence and confirmed transfer deltas; reads do not refresh it.

## Original source and exact patch

Baseline [repository](https://github.com/alicehjjung/CS239_CatchMeIfYouScam_AliceJung),
revision `2fe55f85a51b65819222816cb5b5b71f7d594355`. MIT notice retained.

Added hooks use the `Adaptation code:` comment prefix; new adapter modules carry
the same prefix in their module docstrings.

upstream.patch adds one guarded decorator to each of the three Payments tools and
the Assistant list_payees tool. It adds a host-assigned policy_port attachment.
Existing function bodies remain unchanged, including load_bank/save_bank.
SDK 1 compatibility uses FastMCP and camelCase ToolAnnotations. Optional A2A
imports are deferred until that transport is used; the A2A business path is unchanged.

```python
@guarded(lambda: policy_port, server)
@traced_request
def execute_transfer(recipient: str, amount: float) -> dict:
    ...  # Original bank implementation.
```

The decorator receives the existing policy and MCP server. It reads the caller
name from request _meta.caller, or caller_context for direct Python calls. It binds actual
arguments, converts the policy amount to integer cents, checks permission and then
calls the original function. Its exposed MCP signature adds transfer_request_id as
correlation metadata; the original bank function still receives only recipient and
amount. An intent ID is not proof of confirmation without trusted host facts.

## Files and calls

| File or call | Meaning |
| --- | --- |
| rules.dl | Reviewed initial policy inputs, keys and English-annotated application rules |
| adapter.py: Policy | Connect the shared SDK to this reviewed policy |
| before hook | Record actual server Clock before checking |
| completed hook | Skip delta ingestion when the original callback reports failure |
| after hook | Record only a successful original transfer's confirmed delta |
| tool_adapter.guarded | Add the gate without replacing the original MCP function body |
| tool_adapter.invoke | Read current_caller, normalize actual arguments and invoke Policy.call |
| tool_adapter.record_result | Verify returned account/amount; update policy Balance, DailyBudget, Consumed and Transfer |
| money.py | Exact policy cent conversion; original bank float mechanics remain unchanged |

The old operations.py business reimplementation is removed. All generic keys,
EDB staging, validation and uncertain-effect handling remain in the shared SDK.

## Scope and deployment gaps

The demo starts a fresh policy scope; the supplied mock bank must match reviewed
initial facts. Bank JSON and EDB do not share a transaction. Post-effect mapping
failures stop the session, without claiming that the bank mutation was rolled back.
Restart reconciliation, external drift and bank-day rollover are not implemented.

The original app lacks authenticated confirmation, identity-review and data-lineage
producers. Tests privately ingest synthetic evidence and execute actual registered
MCP handlers over a synthetic temporary bank. Full A2A output isolation and endpoint
authentication remain deployment work. No arbitrary fact-writing tool is exposed.

## Caller names

No caller name is hardcoded in the tool annotation. A host that knows its current
agent name sends it with the MCP request:

```python
await session.call_tool(name, arguments, meta={"caller": agent.name})
```

_meta.caller is this adapter's metadata convention, not a standard authenticated
MCP identity. The receiver reads the actual request metadata. Missing names raise
before the bank action. For direct Python calls, use caller_context(agent.name).
The original external host does not yet send this metadata automatically; it must
add this sender-side line. The offline protocol test exercises real MCP request
messages with assistant/payments names against the same registered transfer tool.
