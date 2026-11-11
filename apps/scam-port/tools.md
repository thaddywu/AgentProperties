# Original payment MCP handlers

lookup_recipient, check_daily_limit and execute_transfer keep their original bodies
and bank JSON access. An added guarded decorator reads the caller name from MCP _meta.caller or direct caller_context and binds actual
arguments, normalizes policy amounts to integer cents and invokes the original
callback only after permission. transfer_request_id is correlation metadata added
by the wrapper; it is not an authorization fact by itself.

After successful execute_transfer, tool_adapter.record_result records its actual
transaction ID/account/amount and updates Balance, DailyBudget, Consumed and
Transfer in one policy EDB batch. Singleton keys replace old policy balances.
The original bank mutation already occurred; no shared bank/EDB transaction is
claimed. Read calls never refresh the entire policy EDB.

Original Assistant.list_payees still reads bank.json and returns masked accounts;
a decorator gates this call. The separate free-text A2A bridge remains outside full
policy coverage. No arbitrary fact-writing agent tool is provided.
