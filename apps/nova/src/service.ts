import {
  ACTIONS,
  applyAction,
  minimalPrevention,
  parseActions,
  parsePreventable,
  speculative,
  terminalQuery,
  whatIf,
  why,
} from "./analysis.js";
import { parseInputs, RULE_TEXT } from "./policy.js";
import { PROTOCOL } from "./protocol.js";
import type { RuntimeState } from "./runtime.js";
import { clone, createEpisode, NovaRuntime, REPLIES, view } from "./runtime.js";
import { allRecords } from "./store-records.js";
export type Selection = { event?: number; side?: "before" | "after" | "check" };
export type Request = Selection & {
  operation: string;
  scope?: string;
  revision?: number;
  preset?: "initial" | "earlier" | "denial";
  query?: string;
  remove?: string;
  add?: string;
  events?: string;
  actions?: string;
  goal?: string;
  basis?: "earlier" | "selected";
  from?: string;
  to?: string;
  id?: string;
  body?: string;
  config?: string;
  trace?: string[];
};
/** Local service boundary. The browser sends intents; policy execution stays here. */
export class NovaService {
  runtime = createEpisode();
  version = 1;
  selected(selection: Selection): RuntimeState {
    if (selection.event === undefined) return this.runtime.snapshot();
    const event = this.runtime.state.events.find((e) => e.seq === selection.event);
    if (!event) throw new Error("Unknown event snapshot.");
    const state = this.runtime.snapshot();
    // Gate inputs are the event's pre-settlement inputs, not its derived witness.
    state.stores = clone(
      selection.side === "before" || (selection.side === "check" && event.kind !== "send")
        ? event.before
        : event.after,
    );
    state.events = state.events.filter((e) => e.seq <= event.seq);
    state.revision = event.seq;
    state.messages = state.messages
      .filter((m) =>
        allRecords(state).some((r) => r.fact.predicate === "Sender" && r.fact.args[1] === m.id),
      )
      .map((m) => ({
        ...m,
        status: allRecords(state).some(
          (r) =>
            r.fact.predicate === "Received" && r.fact.args[0] === m.to && r.fact.args[1] === m.id,
        )
          ? "delivered"
          : allRecords(state).some(
                (r) => r.fact.predicate === "Incoming" && r.fact.args[1] === m.id,
              )
            ? "pending"
            : "denied",
      }));
    return state;
  }
  state(selection: Selection = {}) {
    return {
      ...view(this.selected(selection)),
      version: this.version,
      rules: RULE_TEXT,
      protocol: PROTOCOL,
      liveEvents: clone(this.runtime.state.events),
    };
  }
  run(req: Request) {
    if (req.operation === "state") return this.state(req);
    if (req.revision !== this.version)
      throw new Error("State changed. Refresh the store and rerun.");
    const selected = this.selected(req);
    switch (req.operation) {
      case "query":
        return terminalQuery(selected, req.query ?? "", req.scope);
      case "why":
        return why(selected, req.query ?? "", req.scope);
      case "what-if":
        return whatIf(selected, req.remove ?? "", req.add ?? "", req.query ?? "");
      case "minimal":
        return minimalPrevention(selected, parsePreventable(req.events ?? ""), req.query ?? "");
      case "speculative":
        return speculative(
          req.basis === "earlier" ? createEpisode("earlier").state : selected,
          parseActions(req.actions ?? ""),
          req.goal ?? "",
        );
      case "reset": {
        if (!["initial", "earlier", "denial"].includes(req.preset ?? ""))
          throw new Error("Unknown preset.");
        this.runtime = createEpisode(req.preset);
        break;
      }
      case "send":
        this.runtime.send(req.from ?? "", req.to ?? "", req.id ?? "", req.body ?? "");
        break;
      case "settle":
        this.runtime.settle(req.id ?? "");
        break;
      case "config": {
        const config = parseInputs(req.config ?? "");
        if (
          config.some(
            (f) =>
              !["Auditor", "HasCap", "Requires", "TagGroup", "AuditGoal"].includes(f.predicate),
          )
        )
          throw new Error(
            "Only Auditor, HasCap, Requires, TagGroup and AuditGoal belong in configuration.",
          );
        this.runtime.configure(config);
        break;
      }
      case "advance": {
        const pending = this.runtime.state.messages.find((m) => m.status === "pending");
        if (pending) {
          this.runtime.settle(pending.id);
          break;
        }
        const assignments = [
          { id: "mP0", to: "procurement", tag: "nova_procurement" },
          { id: "mF0", to: "facility", tag: "nova_facility" },
          { id: "m0", to: "hr", tag: "nova_hiring" },
        ];
        const assignment = assignments.find(
          (a) => !this.runtime.state.messages.some((m) => m.id === a.id),
        );
        if (assignment) {
          this.runtime.send(
            "board",
            assignment.to,
            assignment.id,
            `Nova: prepare the ${assignment.tag} budget rationale.`,
            { tag: assignment.tag },
          );
          break;
        }
        const reply = Object.entries(REPLIES).find(
          ([, r]) => !this.runtime.state.messages.some((m) => m.id === r.id),
        );
        if (!reply) throw new Error("Episode complete. Reset or send a custom message.");
        this.runtime.send(reply[0], "auditor_a", reply[1].id, reply[1].body);
        break;
      }
      case "replay-trace": {
        const actions = (req.trace ?? []).map((id) => {
          const action = ACTIONS.find((a) => a.id === id);
          if (!action) throw new Error("Unknown trace action.");
          return action;
        });
        let next = req.basis === "earlier" ? createEpisode("earlier") : new NovaRuntime(selected);
        for (const action of actions) {
          const result = applyAction(next.state, action);
          if (!result.allowed)
            throw new Error("Trace contains a denied action; current runtime was not changed.");
          next = result.runtime;
        }
        this.runtime = next;
        break;
      }
      default:
        throw new Error("Unknown operation.");
    }
    this.version++;
    return this.state();
  }
}
export type NovaView = ReturnType<NovaService["state"]>;
