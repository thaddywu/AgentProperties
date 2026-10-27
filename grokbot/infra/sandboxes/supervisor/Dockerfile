FROM node:22-bookworm-slim
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY grokbot/patches grokbot/patches
COPY grokbot/packages/contracts grokbot/packages/contracts
COPY grokbot/packages/core grokbot/packages/core
COPY runtime runtime
COPY grokbot/packages/logging grokbot/packages/logging
COPY grokbot/infra/sandboxes/supervisor grokbot/infra/sandboxes/supervisor
RUN corepack enable && pnpm install --frozen-lockfile --prod --filter "@rakazo/sandbox-supervisor..."
WORKDIR /app/grokbot/infra/sandboxes/supervisor
CMD ["pnpm", "exec", "tsx", "src/index.ts"]
