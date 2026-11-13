# Original mock bank with incremental policy evidence

The original payment and assistant MCP tools retain their bank JSON operations,
lookup/limit mechanics, masked output and logging. Small decorators add a policy
gate; the transfer wrapper accepts host-issued intent correlation metadata without
changing the original bank function body. SDK 1 compatibility changes are explicit
in upstream.patch; optional A2A imports are deferred until that transport is used.

The policy EDB contains reviewed initial bank observations, host-confirmed intents,
source/review evidence and confirmed transfer deltas. No full-bank mapping runs on
every call. Original float-valued bank mechanics remain; policy arithmetic uses
exact integer cents. Bank and EDB do not share a transaction; uncertain effects
stop the scope. Restart reconciliation is not implemented.

Authenticated confirmation, identity review and source producers are still needed.
Synthetic tests use private host ingestion, not an agent fact-assertion endpoint.
Daily rollover, network authentication and full A2A isolation remain deployment work.
