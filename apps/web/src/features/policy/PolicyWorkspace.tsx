import type { NativePolicyContext, PolicyObservation } from "@rakazo/contracts";
import { Button, Switch } from "@rakazo/ui-web";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useState } from "react";
import { setUiLocale } from "../../lib/i18n";
import { rpc, selectSpace } from "../../lib/rpc";

import { PolicyStoreInspector, StoreInspection } from "./PolicyStoreInspector";

const PolicyMode = createContext(false);
export const usePolicyMode = () => useContext(PolicyMode);
type Context = NativePolicyContext;
export function PolicyWorkspace({ children, userId }: { children: ReactNode; userId: string }) {
  const [context, setContext] = useState<Context | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth >= 1024);
  const [selected, setSelected] = useState<PolicyObservation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    void setUiLocale("en");
    void rpc.policyNative
      .context({})
      .then(setContext)
      .catch(() => setError("Could not load policy mode. Refresh to retry."));
  }, []);
  const toggle = async (enabled: boolean) => {
    if (!context) return;
    setBusy(true);
    setError("");
    try {
      const next = enabled ? await rpc.policyNative.enable({}) : context;
      const fromSpace = context.enabled ? context.policySpaceId : context.originalSpaceId;
      if (fromSpace)
        localStorage.setItem(`policy-route:${userId}:${fromSpace}`, window.location.pathname);
      const toSpace = enabled ? next.policySpaceId! : next.originalSpaceId;
      if (!selectSpace(toSpace)) throw new Error("Could not switch spaces.");
      const path =
        localStorage.getItem(`policy-route:${userId}:${toSpace}`) ??
        (enabled ? `/app/${next.bots.board}` : "/app");
      window.location.assign(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not switch mode.");
      setBusy(false);
    }
  };
  return (
    <PolicyMode.Provider value={context?.enabled ?? false}>
      <div className="flex h-full flex-col">
        <header className="flex h-11 shrink-0 items-center gap-3 border-b border-border px-4">
          <label htmlFor="policy-switch" className="text-xs">
            Use Our Policy
          </label>
          <Switch
            id="policy-switch"
            aria-label="Use Our Policy"
            disabled={!context || busy}
            checked={context?.enabled ?? false}
            onCheckedChange={(value) => void toggle(value)}
          />
          {context?.enabled && (
            <>
              <span className="hidden text-xs text-muted-foreground sm:inline">
                Nova · Messaging only
              </span>
              <Button size="sm" variant="ghost" onClick={() => setInspectorOpen((value) => !value)}>
                Stores
              </Button>
              {context.started && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      const next = await rpc.policyNative.enable({ fresh: true });
                      if (!selectSpace(next.policySpaceId!))
                        throw new Error("Could not switch spaces.");
                      window.location.assign(`/app/${next.bots.board}`);
                    } catch {
                      setError("Could not create a new audit.");
                      setBusy(false);
                    }
                  }}
                >
                  New audit
                </Button>
              )}
              {!context.started && (
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      setContext(await rpc.policyNative.start({}));
                    } catch (e) {
                      setError(e instanceof Error ? e.message : "Could not start audit.");
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Start audit
                </Button>
              )}
            </>
          )}
          {error && (
            <span role="alert" className="text-xs text-destructive">
              {error}
            </span>
          )}
        </header>
        <StoreInspection.Provider
          value={(observation) => {
            setSelected(observation);
            setInspectorOpen(true);
          }}
        >
          <div className="relative flex min-h-0 flex-1">
            <div className="min-w-0 flex-1">{children}</div>
            {context?.enabled && inspectorOpen && (
              <PolicyStoreInspector selected={selected} onClose={() => setInspectorOpen(false)} />
            )}
          </div>
        </StoreInspection.Provider>
      </div>
    </PolicyMode.Provider>
  );
}
