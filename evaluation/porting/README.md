# Agentic port-in

The generic local Codex path is now available separately from the historical
LabCluster-only controller below. It copies a Git checkout, reads `policy.md`
(`policies.md`/`POLICY.md` also supported) and `app.md` when present, and produces
a candidate with adapters/rules, tests, logs and independent execution readings.
Read the shared [port contract](../../translation/python/policy_translation/porting-contract.md).
It disallows new business tools and policy decisions hidden in adapters.

```bash
docker build -f evaluation/porting/Dockerfile -t policy-portin:local .
docker build -f evaluation/porting/Dockerfile.batch -t policy-portin:batch-v1 .
python3 evaluation/codex_port.py --source /path/to/student-repo \
  --output evaluation/output/new-port --connection /path/to/private-connection.json
```

This checkout-only adapter requires Docker and an installed standalone Codex CLI.
Connection settings use `baseUrl`, `modelId`, `apiKey`, optional `reasoningEffort`;
the endpoint must implement the Responses protocol used by Codex. The optional
adapter does not change the provider-neutral core. Credentials stay in a host
relay, never inside application containers. Containers have no general network,
read-only original/framework mounts, and an independent writable candidate.
Codex's internal sandbox is disabled only inside this external Docker boundary.

Use `--policy relative/path.md` for ambiguous/nonstandard policy locations.
Use `--stage translate` or `--stage backtranslate` to run stages separately.
The default `all` performs inspection/edit/test/repair, independent reverse reading,
then a separate sentence-alignment session. Original policies/documents/tests are
checked for changes. Positive/negative development tests execute actual callbacks
in fresh containers; remote model dependencies may use labeled offline fixtures.
These checks do not prove semantic correctness or complete mediation. Failed
attempts remain saved. A new forward translation requires a new output directory.
Reverse runs are versioned and cannot see original policy, forward plan or tests;
their citations and rule coverage are checked, not their semantic equivalence.

To start both buttons and the existing review panel for a new checkout:

```bash
python3 evaluation/run.py --repo /path/to/student-repo \
  --port-output evaluation/output/new-port --data evaluation/output/new-study \
  --connection /path/to/private-connection.json --port 5193
# Resume/view an existing copied port:
python3 evaluation/run.py --codex-port evaluation/output/new-port \
  --data evaluation/output/new-study --connection /path/to/private-connection.json
```

The server operator selects the repository and connection once; browser requests
only select Translate or Back-translate. Jobs run in the backend, save progress
across page reloads, and preserve review versions/judgments. Back-translate also
aligns the frozen descriptions and loads the new version. Export retains
recorded development trajectories; arbitrary repos do not automatically acquire
an RQ3 reset/replay connector. Use their backend-specific test files and traces.
No universal app frontend is introduced.

---

This runnable profile takes an **original LabCluster Git checkout and its original
six-section Markdown policy**, creates isolated original/candidate copies, and
uses a model to inspect source, write a new fact mapper and Datalog rules, run
checks and repair failures. It does not read the existing hand-authored
`apps/labcluster-port` adapter, rules or patch. The business files remain unchanged.

From the repository root:

```bash
docker build -f evaluation/porting/Dockerfile -t policy-portin:local .
python3 evaluation/port.py \
  --source /path/to/original-labcluster \
  --policy /path/to/original-labcluster/policies.md \
  --connection /path/to/private-connection.json \
  --output evaluation/output/my-port
python3 evaluation/run.py --ported-app evaluation/output/my-port \
  --data evaluation/output/my-study --port 5192
```

The model connection uses the same generic `baseUrl`, `modelId`, `apiKey` and
`maxTokens` shape as the [evaluation workbench](../README.md#model-connection).
For a compatible reasoning model, the optional shared setting
`"reasoningEffort": "high"` is useful for source and rule repairs; unsupported
settings produce a provider error rather than a silent downgrade.
`timeoutSeconds` can be set up to 600 for longer reasoning calls (default 180).
For the porting loop, allow enough completion tokens for both reasoning and code;
the tested configuration used `maxTokens: 32000`, `reasoningEffort: "high"` and
`timeoutSeconds: 600`. These are connection settings, not engine requirements.
Keep that file outside the repository. A local compatible model is supported;
no hosted vendor is required. Installed entry points are `policy-port` and
`policy-evaluate`. Docker and the prepared image are required for this profile;
the host does not need Soufflé. The image contains the pinned engine and the
independent Python stack, without Grokbot or the reference application port.
Each sandbox image also receives a local `policy-portin:retained-…` tag. Keep
these tags for saved studies; moving the ordinary build tag must not remove the
manifest needed to replay an older study.

The operator starts porting. Students subsequently review categories and
translation fidelity without editing Python, Datalog or the connection. Test
files run separately through the command-line runner. Browser requests cannot
select source paths, executable code or model credentials.

## What the loop actually does

1. Copy selected tracked source files and preserve their content hashes. Preserve
   the supplied policy document separately. Original and candidate are separate
   directories; the user's checkout is never changed.
2. Require inspection of the supplied policy and the tool, store and messaging
   interfaces. The model can request bounded source reads and write only three
   generated files: `adapter.py`, `rules.dl`, `plan.json`.
3. Validate the mapper restrictions, schema, rules and source-policy mapping.
   Execute immutable development checks inside a fresh container. Feed real
   errors and failed assertions back to the model. Every edit invalidates prior
   successful checks. A model `finish` action cannot approve a failing candidate.
4. Run a separate held-out suite only after development passes. Its tests and
   outcomes are not available as model tools. A failure remains a failed port;
   it is not silently repaired against the held-out answers.
5. Independently back-translate the actual rules, mapper and relevant original
   implementation. This call receives no original policy or porting history.
   Preserve many-to-many mappings to the original six policy sections. The
   sections are not yet adjudicated atomic requirements.
6. Load the accepted artifacts into the workbench. Run original and protected
   versions from fresh identical state and store actual operation evidence,
   state changes, original application traces and human judgments.

The controller has a bounded turn budget. Its private output contains model
responses, tool results, edit diffs, failed checks, source/artifact/image hashes,
coverage limitations, independent validation and the back-translation. No
reference fallback substitutes for model failure. Resume an interrupted or
exhausted run with its original pinned image and log:

```bash
python3 evaluation/port.py --resume --output evaluation/output/my-port \
  --connection /path/to/private-connection.json --max-turns 45
```

Resume increases the total turn limit, up to 120, and requires checks to pass again.
It does not erase failed attempts. Held-out results must not be used to tune the
same research test set. Keep all output private: it contains source documents and
trajectories, and is ignored by Git.

For engineering repair after independent validation fails, opt in explicitly:

```bash
python3 evaluation/port.py --resume --repair-validation \
  --output evaluation/output/my-port \
  --connection /path/to/private-connection.json --max-turns 60
```

The initial artifacts and independent result are archived unchanged under
`validation-history/initial/`. The agent may now see failures and run the exposed
cases as a `regression` suite. Static, development and regression checks must all
pass. `heldout.json` keeps the first result; `regression.json` records the later
result, and the final status is `validated-after-repair`. These repaired results
are **not independent held-out accuracy**. The workbench export preserves both.

## Boundaries of this first profile

The framework-owned integration driver mediates `Trace.tool` and `Bus.send`.
This catches both ordinary tools and the original legacy callback that bypasses
`Tools.call`. The generated mapper receives copies of real store state, the bound
request and synthetic fixtures; it cannot supply caller identity or execute
business effects. The policy gate calls the **original callback** only after
authorization. The original access checks, scheduler, receipts and transactions
remain in place. Acceptance is not proof of full policy coverage.

The container has no network, credentials or writable source mount, and has a
read-only root, unprivileged user, resource/time limits and dropped capabilities.
AST restrictions narrow the generated mapper; they are not the isolation boundary.
This is intended for the known simulator, not as a hardened service for arbitrary
hostile repositories. A Docker daemon remains an operator-trusted dependency.

This is **not yet a general automatic instrumenter for arbitrary applications**.
A new backend requires a trusted profile defining effect boundaries, authoritative
observations, reset/replay and independent acceptance checks. The model generates
the policy mapping inside that boundary. Direct Store access, other communication
channels, semantic paraphrases of private data, distributed minimal fact placement
and concurrent/remote atomicity are outside this profile's guarantees. Exact
synthetic private-value matching must not be reported as general information-flow
control. The generated coverage plan records delegation to original application
checks as well as gaps.

Runs currently selects original deterministic multi-agent scenarios or targeted
challenge cases. The student's note records intent; it is not an agent prompt.
The seed is retained for the record but does not randomize this deterministic
runner. Porting uses a real model; these RQ3 executions do not use a live model.
Students can label operation attempts, actual violations and false blocks using
the stored before/after state and messages. Export retains unknown judgments.
Container startup and engine work are included in end-to-end elapsed time;
per-operation timings are separate. Neither number is a universal overhead claim.

The 17 development cases include positive workflows as well as over-quota
admission, cross-owner reads/messages, forged receipts, stop failure and delayed
release. Six held-out cases vary quota dimensions, exact boundaries, nested
payloads, allocation generation and invalidated approval. Keep new student study
cases separate from these port acceptance suites.
