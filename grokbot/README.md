# Grokbot host

The existing Rakazo/Grokbot implementation is grouped here: `apps/` contains web UI, API, worker, Electron, Expo and the marketing site; `packages/` contains host domain logic, adapters, contracts, persistence and shared UI.

Nova's UI customization remains in `apps/web/src/features/nova/`. Its application code and reference policies live in the repository's `apps/nova/`; generic policy evaluation lives in `runtime/`; natural-language translation lives in `translation/`. The host consumes these workspace packages instead of owning a second copy of Nova.

Workspace configuration, lockfile, operational scripts and infrastructure remain at the repository root. Run `pnpm` commands and `./nova-demo.sh` there. See `../docs/repository-structure.md`.

For the full host, use [source or published-image setup](../docs/self-host.md). The separate five-principal LLM chat demonstration is documented in [native policy chat](docs/native-policy.md); it is not the six-principal Nova application.
