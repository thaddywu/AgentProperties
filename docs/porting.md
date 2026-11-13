# Application porting

The generic rule translator accepts an existing trusted binding. The optional application-port adapter also inspects source, adds instrumentation, tests original callbacks and independently reads the candidate implementation back. These are different entry points.

```bash
policy-translate /path/to/policy.md --binding /path/to/runtime.json \
  --connection /path/to/private-connection.json --output output/draft
```

The optional application-port workflow requires Docker, Linux x86_64 and a standalone Codex CLI. Build its isolated execution images:

```bash
docker build -f src/policyscope/adapters/Dockerfile -t policy-portin:local .
docker build -f src/policyscope/adapters/Dockerfile.batch -t policy-portin:batch-v1 .
policyscope add /path/to/original-app /path/to/enforced-app \
  --connection /path/to/private-connection.json
```

The original app is a clean Git checkout with `app.md` and `policy.md`. The target must be absent or empty. Debug flags can select existing document names without rewriting them. Git branches remain user-owned. The adapter preserves original documents, tests and business behavior; it adds rules, mediation and explicit fact producers. Passing development tests does not prove full policy fidelity or complete mediation.

Connection files are private, outside the repository:

```json
{
  "baseUrl": "https://MODEL-ENDPOINT.example/v1",
  "modelId": "MODEL_ID",
  "apiKey": "YOUR_API_KEY",
  "reasoningEffort": "medium"
}
```

The compatible transport uses chat completions. The optional coding-agent adapter uses its Responses-compatible connection. Other transports can implement the injected `generate(stage, prompt)` boundary. No particular hosted provider is required by the core.

Credentials remain in the host relay, outside application containers. Original/framework mounts are read-only; application checks run in credential-free containers without general network access. Logs, source snapshots, failed attempts, model usage and generated trajectories stay in private output directories. The shared [port contract](../src/policyscope/policy_adder/porting-contract.md) states the exact adaptation obligations and limits.

```bash
policyscope review --back-translation /path/to/enforced-app/back-translation \
  --policy /path/to/original-app/policy.md
```

The LabCluster-specific generator, scenario runner and replay loader remain under `policyscope.adapters.labcluster`; select `policyscope port-profile --help` for that profile. A different application still needs its own reset/replay and authoritative observation integration. The generic port adapter does not automatically supply a research runner for every repository.
