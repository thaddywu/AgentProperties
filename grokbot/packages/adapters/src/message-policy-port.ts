import { EffectNotAppliedError } from "@rakazo/policy-runtime/application";
import type { ObservationBinding } from "@rakazo/policy-runtime/backend-port";
import { createBackendPort } from "@rakazo/policy-runtime/backend-port";
import type { MessagingProfile } from "@rakazo/policy-runtime/messaging";

type RunContext = { id: string; spaceId: string; userId: string; botId: string };

/** Composition-root adapter. Policy facts and decisions contain logical principals, not DB IDs. */
export function createGrokbotMessagePort(options: {
  spaceId: string;
  userId: string;
  principalByBot: Record<string, string>;
  profile: MessagingProfile;
  observations?: ObservationBinding[];
  deliver: (message: {
    id: string;
    fromBotId: string;
    toBotId: string;
    body: string;
  }) => Promise<void>;
}) {
  const principalByBot = structuredClone(options.principalByBot);
  const botByPrincipal = new Map(
    Object.entries(principalByBot).map(([bot, principal]) => [principal, bot]),
  );
  if (
    botByPrincipal.size !== Object.keys(principalByBot).length ||
    [...botByPrincipal.keys()].some((p) => !options.profile.principals.includes(p))
  )
    throw new Error("Bot bindings must map distinct backend identities to admitted principals.");
  const port = createBackendPort({
    profile: options.profile,
    observations: options.observations,
    async deliver(message) {
      const fromBotId = botByPrincipal.get(message.from),
        toBotId = botByPrincipal.get(message.to);
      if (!fromBotId || !toBotId)
        throw new EffectNotAppliedError("No registered bot delivery route.");
      await options.deliver({ id: message.id, fromBotId, toBotId, body: message.body });
    },
  });
  return {
    forRun(run: RunContext) {
      if (run.spaceId !== options.spaceId || run.userId !== options.userId)
        throw new Error("Run is outside this adapter's authenticated scope.");
      const principal = principalByBot[run.botId];
      if (!principal) throw new Error("Run has no registered principal.");
      const agent = port.bind(principal);
      return {
        send(input: { recipientBotId: string; deliveryKey: string; message: string }) {
          const recipient = principalByBot[input.recipientBotId];
          if (!recipient || !input.deliveryKey)
            throw new Error("A message needs a registered recipient and stable delivery key.");
          return agent.send(recipient, `${run.id}:${input.deliveryKey}`, input.message);
        },
        query: agent.query,
        accessible: agent.accessible,
      };
    },
    ingest: port.ingest,
    reconcile: port.reconcile,
    snapshot: port.snapshot,
  };
}
