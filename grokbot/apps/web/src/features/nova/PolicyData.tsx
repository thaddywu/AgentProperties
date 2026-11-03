type Transfer = {
  export: string;
  import: string;
  to?: string;
  requireRole?: string;
  messageArgument?: number;
  retain?: string;
};
type Protocol = {
  replicated: readonly string[];
  local: Record<string, string[]>;
  onlyAt?: Record<string, string>;
  temporary?: readonly string[];
  observer?: readonly string[];
  message?: Transfer;
  transfers?: Record<string, Transfer>;
};

export function ProtocolView({ protocol }: { protocol: Protocol }) {
  const transfers = protocol.transfers ?? (protocol.message ? { message: protocol.message } : {});
  return (
    <div className="space-y-4 text-xs">
      <p>
        <strong>Copied to every principal:</strong> {protocol.replicated.join(", ") || "None"}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <caption className="mb-2 text-left font-medium">Local storage and inference</caption>
          <thead>
            <tr className="border-b border-border">
              <th className="p-2">Predicate</th>
              <th className="p-2">Location / argument restriction</th>
            </tr>
          </thead>
          <tbody>
            {[
              ...new Set([...Object.keys(protocol.local), ...Object.keys(protocol.onlyAt ?? {})]),
            ].map((name) => (
              <tr key={name} className="border-b border-border">
                <td className="p-2 font-mono">
                  {name}
                  {protocol.local[name]
                    ? `(${protocol.local[name].map((arg) => (arg === "@self" ? "self" : arg)).join(", ")})`
                    : ""}
                </td>
                <td className="p-2">
                  {protocol.onlyAt?.[name]
                    ? `Only at ${protocol.onlyAt[name]}`
                    : protocol.local[name]?.includes("@self")
                      ? "self = this principal"
                      : "In a store containing the required local inputs"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted-foreground">
        _ accepts any value already present locally; it does not copy facts from other stores.
      </p>
      {protocol.observer?.length ? (
        <p>
          <strong>Global query only:</strong> {protocol.observer.join(", ")}. Never used by a local
          receive gate.
        </p>
      ) : null}
      {protocol.temporary?.length ? (
        <p>
          <strong>Removed after the receive check:</strong> {protocol.temporary.join(", ")}
        </p>
      ) : null}
      {Object.entries(transfers).map(([name, transfer]) => (
        <section key={name} className="space-y-1 rounded border border-border p-3">
          <h4 className="font-medium">
            {name === "message"
              ? "Message transfer"
              : name === "audit"
                ? "Audit receipt transfer"
                : name}
          </h4>
          <p className="font-mono">
            {transfer.export} → {transfer.import}
          </p>
          <p>Destination: {transfer.to ?? "message recipient"}</p>
          {transfer.messageArgument !== undefined && (
            <p>
              Export only this message's facts (message ID in argument{" "}
              {transfer.messageArgument + 1}).
            </p>
          )}
          {transfer.requireRole && <p>Exporter must hold role: {transfer.requireRole}</p>}
          {transfer.retain && (
            <p>
              {transfer.retain === "on-allow"
                ? "Incoming tags are temporary during the check. Keep on allow; discard on deny."
                : transfer.retain}
            </p>
          )}
        </section>
      ))}
    </div>
  );
}

const labels: Record<string, string> = {
  golden: "Reference",
  translated: "Generated",
  allowed: "Allowed",
  expected: "Expected allow",
  denyDerived: "Deny derived locally",
  fullCopyDeny: "Deny with full copy",
  received: "Successful receipt recorded",
  bodyVisible: "Content visible to recipient",
  missingFacts: "Missing facts",
  extraFacts: "Extra facts",
  decisionsChanged: "Delivery decisions changed",
  visibilityChanged: "Recipient visibility changed",
  localDeny: "Deny locally",
  localUnionCount: "Facts in union of local stores",
  fullCopyCount: "Facts with full copy",
  storedInputCopies: "Stored input copies",
  fullCopyInputCopies: "Input copies with full replication",
};
const label = (key: string) =>
  labels[key] ?? key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (c) => c.toUpperCase());

/** Read-only evidence: preserve all fields, but do not expose JSON serialization as prose. */
export function PolicyData({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>—</span>;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (typeof value !== "object")
    return (
      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
        {String(value)}
      </pre>
    );
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted-foreground">None</span>;
    return (
      <ul className="space-y-2">
        {value.map((item, index) => (
          <li key={index} className="border-l border-border pl-3">
            <PolicyData value={item} />
          </li>
        ))}
      </ul>
    );
  }
  const record = value as Record<string, unknown>;
  if (typeof record.path === "string" && typeof record.content === "string")
    return (
      <details>
        <summary className="cursor-pointer font-medium">{record.path}</summary>
        <div className="mt-2">
          <PolicyData value={record.content} />
        </div>
      </details>
    );
  return (
    <dl className="space-y-2">
      {Object.entries(record).map(([key, item]) => (
        <div key={key} className="grid gap-1 sm:grid-cols-[minmax(8rem,1fr)_3fr]">
          <dt className="font-medium">{label(key)}</dt>
          <dd className="min-w-0">
            <PolicyData value={item} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ProtocolDetails({ title, protocol }: { title: string; protocol: Protocol }) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer font-medium">{title}</summary>
      <div className="mt-3">
        <ProtocolView protocol={protocol} />
      </div>
    </details>
  );
}
