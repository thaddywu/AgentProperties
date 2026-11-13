# Examples

| Directory | Purpose |
| --- | --- |
| [quickstart](quickstart/quickstart.py) | Minimal guarded Python callback |
| [applications/labcluster-port](applications/labcluster-port/README.md) | Reviewed adapter, rules and reference readings for LabCluster |
| [applications/scam-port](applications/scam-port/README.md) | Payment-tool adapter and explicit evidence gaps |
| [cases](cases/README.md) | Synthetic comparison inputs |

Application examples keep their own policy documents, source-binding metadata and tests together. They are not framework modules. The LabCluster reference also exercises immutable review import in the offline suite. Its runner and original upstream integration are optional.

Run from the repository root after installing the package:

```bash
python examples/quickstart/quickstart.py
policyscope run-cases --cases examples/cases/document-tests.json --data ../policyscope-runs/example
```
