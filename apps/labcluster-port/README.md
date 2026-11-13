# LabCluster policy adapter

Read [ADAPTATION.md](ADAPTATION.md) and the [PolicyScope guide](../../src/policyscope/enforcement/README.md).
The original Store, business methods, agents, tool names and trace remain intact.
The upstream patch adds explicit guarded execution inside Tools.call and a
completion-report decorator. Original Store business methods remain intact.

The SDK guards the original callback. The tool branches call policy.put directly; tool_facts.py shares receipt/release assignments. Provenance facts are written explicitly. It never reads
Store.snapshot. The original app may still use snapshots for its own logic/trace.
Initial policy configuration and English rule explanations live in rules.dl.

```bash
PYTHONPATH=src python3 apps/labcluster-port/run.py --upstream /path/to/pinned-checkout
PYTHONPATH=src python3 apps/labcluster-port/tests/verify.py --upstream /path/to/pinned-checkout
```

This demonstration starts with a fresh original Store and policy scope. Store and
EDB do not share a transaction: a post-effect mapping failure stops the session,
without claiming to undo the original operation. Restart reconciliation is not
implemented. Structured COMPLETION_REPORT messages are checked before delivery.
Other message types and the original injected unsafe T4 callback remain outside
that message guard. No real cluster, hosted model or full IFC claim is required.
The upstream MIT notice is preserved in UPSTREAM-LICENSE.
