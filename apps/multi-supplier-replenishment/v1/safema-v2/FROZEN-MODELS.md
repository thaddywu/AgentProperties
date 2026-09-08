# Frozen SafeMA v2 executable artifacts

Frozen after successful Step 9 mechanism validation on 2026-09-08.

| Artifact | SHA-256 |
|---|---|
| `models/api-effects-v2.yaml` | `256fc3c020090a374656b28bac84d679789cfe39b873c61b73670411457ebd67` |
| `models/trusted-origins-v2.yaml` | `72161b2717038772963f56e67f4a1ed90f942a3fa62e27b4747c13b043c4abfc` |
| `models/trusted-state-resolvers-v2.yaml` | `b644891388682ec396cd872af29fc5e8849b2900821844434c465afa1bfba226` |
| `policies/replenishment-purchase-v2.yaml` | `f4730ad88b2da2f78c3344ef17f0345d8d456b4265b32742a261d43abe572b5c` |

Later experiments must not silently alter these model semantics. A changed
model requires a new version and a new baseline/treatment evaluation.
