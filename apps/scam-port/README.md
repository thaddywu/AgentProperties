# Original payment MCP tools with policy hooks

Read [ADAPTATION.md](ADAPTATION.md) and the [PolicyScope guide](../../src/policyscope/enforcement/README.md).
Original bank.json load/save, transfer mechanics, masked payee output and logging
remain intact. Added decorators guard calls; confirmed transfer deltas update the
policy EDB. No per-call full-bank projection runs.

```bash
PYTHONPATH=src python3 apps/scam-port/tests/verify.py --upstream /path/to/pinned-checkout
PYTHONPATH=src python3 apps/scam-port/run.py --upstream /path/to/pinned-checkout --bank /path/to/reviewed-mock-bank.json
```

The initial mock bank must match the reviewed policy seeds. This demo starts a
fresh policy scope; bank/EDB restart reconciliation is not implemented. They do
not share a transaction, so uncertain post-effect failures stop the scope.
Authenticated confirmation/review/source producers and full A2A information
isolation remain explicit gaps. No real bank or new model experiment is claimed.
Original prompt sources and the MIT notice are retained.
