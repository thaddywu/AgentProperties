# Repository structure

```text
grokbot/                 Existing host implementation, including UI customizations
  apps/                  web, api, worker, desktop, mobile, www
  packages/              host domain/adapters/contracts/database/shared UI
apps/
  nova/
    app.md               Application specification and interaction description
    policy.md            Natural-language application requirements
    tools.md
    agents/
    episodes/            Optional examples; not part of the execution interface
    src/                 Nova application, reference rules, protocol and analyses
    tests/
runtime/                 Generic Datalog, queries, native provenance and lifecycle
translation/             One-shot natural-language-to-Datalog research prototype
infra/, scripts/         Operational tooling shared by the workspace
```

The dependency direction is `Grokbot UI → Nova application → policy runtime`. Translation reads an application's Markdown; its optional model adapter comes from Grokbot's existing provider-neutral connection/runtime stack. Reference policies are loaded only after model generation. Generated rules are not installed into the application.

The UI remains in Grokbot. Nova can also run without it using `pnpm --filter @rakazo/nova start`. The runtime package has no dependency on Grokbot or Nova. Nova-specific action search and local-store coordination remain with the application because their available actions, principals and protocol are domain-specific; generic evaluation/provenance live in `runtime/`.

For future student applications, this separates requirements/source code from a runtime binding. We have not defined a universal porting API, forced a coordinator/workflow, or implemented automatic source-code conversion. A future binding must identify trusted observations, actions, the enforcement point and any domain-specific analysis actions. The present Nova binding is evidence for that design, not a finalized standard.

Our application-description interface is app.md, policy.md, tools.md and agents/*.md. LLM agents document their actual system prompts; scripted agents document their actual decision logic. Episodes are optional examples, not required for translation, standalone execution or a runtime binding. The existing loader and tests accept an application without episodes/. Nova keeps two illustrative examples. Course-only submission requirements do not define the framework contract; no archives are generated. Source/README and package metadata are not required translator inputs.
