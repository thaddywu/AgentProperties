import type { NovaView } from "@rakazo/nova/service";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@rakazo/ui-web";

export function PolicyLayers({
  state,
  open,
  onOpenChange,
}: {
  state: NovaView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-3xl">
        <DialogTitle>Rules and inputs</DialogTitle>
        <Tabs defaultValue="builtin">
          <TabsList aria-label="Policy layers">
            {state?.policyLayers.map((layer) => (
              <TabsTrigger key={layer.id} value={layer.id}>
                {layer.title}
              </TabsTrigger>
            ))}
          </TabsList>
          {state?.policyLayers.map((layer) => {
            const values = state.configuration.filter((fact) =>
              layer.predicates.some((predicate) => predicate.name === fact.predicate),
            );
            return (
              <TabsContent key={layer.id} value={layer.id} className="min-w-0 space-y-4">
                <p className="text-xs text-muted-foreground">
                  {layer.id === "builtin"
                    ? "Fixed IFC and capability rules. Configuration values come from the app."
                    : "Handwritten Nova rules; the app-specific translation target."}
                </p>
                <section aria-label={`${layer.title} EDB`} className="space-y-2">
                  <h3 className="text-xs font-medium">EDB · input schema</h3>
                  <div className="space-y-1 text-xs">
                    {layer.predicates
                      .filter((predicate) => predicate.kind === "input")
                      .map((predicate) => (
                        <div
                          key={predicate.name}
                          className="flex flex-wrap justify-between gap-x-3 gap-y-1"
                        >
                          <code className="break-all">
                            {predicate.name}({predicate.args.join(", ")})
                          </code>
                          <span className="text-muted-foreground">{predicate.source}</span>
                        </div>
                      ))}
                  </div>
                  {values.length > 0 && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted-foreground">
                        App-supplied values
                      </summary>
                      <pre className="mt-2 whitespace-pre-wrap break-words">
                        {values
                          .map((fact) => `${fact.predicate}(${fact.args.join(", ")}).`)
                          .join("\n")}
                      </pre>
                    </details>
                  )}
                </section>
                <details className="text-xs">
                  <summary className="cursor-pointer font-medium">IDB · derived schema</summary>
                  <div className="mt-2 space-y-1">
                    {layer.predicates
                      .filter((predicate) => predicate.kind === "derived")
                      .map((predicate) => (
                        <code key={predicate.name} className="block break-all">
                          {predicate.name}({predicate.args.join(", ")})
                        </code>
                      ))}
                  </div>
                </details>
                <section aria-label={`${layer.title} rules`} className="space-y-3">
                  <h3 className="text-xs font-medium">Inference rules · {layer.rules.length}</h3>
                  {layer.rules.map((rule) => (
                    <div key={rule.id} className="rounded border border-border p-3">
                      <p className="mb-2 text-xs text-muted-foreground">{rule.id}</p>
                      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                        {rule.text}
                      </pre>
                    </div>
                  ))}
                </section>
              </TabsContent>
            );
          })}
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
