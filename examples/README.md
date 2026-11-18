# Examples

| Directory | Purpose |
| --- | --- |
| [quickstart](quickstart/quickstart.py) | Minimal guarded Python callback |
| [applications/scam-port](applications/scam-port/README.md) | Payment-tool adapter and explicit evidence gaps |
| [cases](cases/README.md) | Synthetic comparison inputs |
| [connection.yaml](connection.yaml) | Empty-key model connection template; copy outside the repository |

Application examples keep their own policy documents, source-binding metadata and tests together. They are not framework modules.

Run from the repository root after installing the package:

```bash
python examples/quickstart/quickstart.py
policyweave run-cases --cases examples/cases/document-tests.json --data ../policyweave-runs/example
```
