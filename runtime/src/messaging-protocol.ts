/** Fixed messaging placement and transport contract. Adapters implement its event hooks. */
export const MESSAGING_PROTOCOL = {
  replicated: ["Requires", "TagGroup"],
  local: {
    HasCap: ["@self", "_"],
    Sender: ["@self", "_"],
    Received: ["@self", "_"],
    Incoming: ["@self", "_"],
    TrustedSource: ["_", "_"],
    TransportTag: ["_", "_"],
    ReceivedBeforeSend: ["_", "_"],
    MayDependOn: ["_", "_"],
    MessageTag: ["_", "_"],
    HasReceivedTag: ["@self", "_"],
    Deny: ["_", "_"],
  } as Record<string, string[]>,
  temporary: ["Incoming"],
  message: {
    export: "MessageTag",
    import: "TransportTag",
    messageArgument: 0,
    retain: "on-allow",
  },
} as const;
