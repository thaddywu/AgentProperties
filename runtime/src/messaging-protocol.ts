/** Fixed messaging placement and transport contract. Adapters implement its event hooks. */
export const MESSAGING_PROTOCOL = {
  replicated: ["Requires", "TagGroup"],
  local: {
    HasCap: ["@self", "_"],
    Sender: ["@self", "_"],
    Receiver: ["@self", "_"],
    Received: ["@self", "_"],
    Incoming: ["@self", "_"],
    TrustedSource: ["_", "_"],
    TransportTag: ["_", "_"],
    Before: ["_", "_"],
    DependsOn: ["_", "_"],
    Propagated: ["_", "_"],
    Knows: ["@self", "_"],
    DenyReceive: ["@self", "_"],
  } as Record<string, string[]>,
  temporary: ["Incoming"],
  message: {
    export: "Propagated",
    import: "TransportTag",
    messageArgument: 0,
    retain: "on-allow",
  },
} as const;
