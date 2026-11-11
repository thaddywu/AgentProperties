import { randomUUID } from "node:crypto";
import { createInterface } from "node:readline";
import type { Readable, Writable } from "node:stream";
import { createActionPort } from "./action-port.js";
import type { ActionContext, EffectOutcome, ExecutionResult, PolicyBundle } from "./application.js";
import { EffectNotAppliedError, EffectUncertainError } from "./application.js";
import type { PolicyFact } from "./datalog.js";
import type { ObservationSnapshot } from "./observations.js";

const MAX_LINE = 1_048_576;
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
type Pending = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};
type BridgeConfig = {
  binding: unknown;
  bundle: PolicyBundle;
  inputs?: PolicyFact[];
  observations: { id: string; predicates: string[] }[];
  operations: { action: string; observations?: string[]; reads?: string[] }[];
};

/** Private parent/child pipe, not a network authorization endpoint or an agent-facing tool. */
export async function servePolicyBridge(
  input: Readable,
  output: Writable,
  callbackTimeoutMs = 30_000,
) {
  const lines = createInterface({ input, crlfDelay: Infinity });
  const pending = new Map<string, Pending>();
  let closed = false;
  let queue = Promise.resolve();
  let port: ReturnType<typeof createActionPort> | undefined;
  const projectResult = (result: ExecutionResult<unknown>) => {
    // Proofs stay on the trusted in-process API, rather than duplicating them in pipe replies.
    const { evidence: _evidence, ...decision } = result.decision;
    return { ...result, decision };
  };
  const serialize = (value: unknown) => {
    const line = JSON.stringify(value);
    if (Buffer.byteLength(line, "utf8") > MAX_LINE)
      throw new Error("Bridge message exceeds the size limit.");
    return line;
  };
  const write = (value: unknown) => {
    output.write(`${serialize(value)}\n`);
  };
  const callback = (kind: string, context: ActionContext, name?: string) =>
    new Promise<unknown>((resolve, reject) => {
      if (closed) return reject(new Error("Backend pipe closed."));
      const id = randomUUID();
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error("Backend callback timed out."));
      }, callbackTimeoutMs);
      pending.set(id, { resolve, reject, timer });
      try {
        write({ type: "callback", id, kind, name, context });
      } catch (error) {
        clearTimeout(timer);
        pending.delete(id);
        reject(error);
      }
    });
  const configure = (value: unknown) => {
    if (
      port ||
      !record(value) ||
      !Array.isArray(value.observations) ||
      !Array.isArray(value.operations)
    )
      throw new Error(
        "Configure this trusted pipe exactly once with registered sources and operations.",
      );
    const config = value as BridgeConfig;
    if (config.operations.some((operation) => operation.reads?.length))
      throw new Error("Gate-derived operation rows require the Python worker.");
    port = createActionPort({
      binding: config.binding,
      bundle: config.bundle,
      inputs: config.inputs,
      observations: config.observations.map((source) => ({
        ...source,
        read: async (context) =>
          (await callback("observe", context, source.id)) as ObservationSnapshot,
      })),
      operations: config.operations.map((operation) => ({
        ...operation,
        execute: async (context) => {
          const outcome = (await callback(
            "effect",
            context,
            operation.action,
          )) as EffectOutcome<unknown>;
          // Leave bounded space for the request/decision envelope before committing runtime state.
          if (Buffer.byteLength(JSON.stringify(outcome), "utf8") > MAX_LINE / 2)
            throw new Error("Effect result exceeds the bridge limit.");
          return outcome;
        },
      })),
      transaction: async (context, run) => {
        try {
          await callback("begin", context);
          const result = await run();
          // Validate the full reply before asking the backend to commit; include the largest legal ID.
          serialize({
            type: "result",
            id: "x".repeat(128),
            ok: true,
            value: projectResult(result),
          });
          await callback("commit", context);
          return result;
        } catch (error) {
          const rollback = await callback("rollback", context).catch(() => null);
          if (record(rollback) && rollback.notApplied === true)
            throw new EffectNotAppliedError("Backend confirmed transaction rollback.");
          throw error;
        }
      },
    });
    return { policyHash: port.policyHash };
  };
  const dispatch = async (method: unknown, params: unknown) => {
    if (method === "configure") return configure(params);
    if (!port || !record(params)) throw new Error("The backend pipe must be configured first.");
    switch (method) {
      case "execute":
        if (
          typeof params.actor !== "string" ||
          typeof params.action !== "string" ||
          (params.resource !== undefined && typeof params.resource !== "string")
        )
          throw new Error("Invalid action intent.");
        {
          const result = await port.execute({
            actor: params.actor,
            action: params.action,
            resource: params.resource,
            parameters: params.parameters as Record<string, string> | undefined,
          });
          return projectResult(result);
        }
      case "query":
        if (typeof params.source !== "string") throw new Error("Invalid query.");
        return port.query(params.source);
      default:
        throw new Error("Unknown backend bridge operation.");
    }
  };
  lines.on("line", (line) => {
    let message: unknown;
    try {
      if (Buffer.byteLength(line, "utf8") > MAX_LINE) throw new Error();
      message = JSON.parse(line);
    } catch {
      write({
        type: "result",
        id: null,
        ok: false,
        error: { code: "protocol_error", message: "Invalid bridge message." },
      });
      return;
    }
    if (!record(message) || typeof message.id !== "string" || message.id.length > 128) {
      write({
        type: "result",
        id: null,
        ok: false,
        error: { code: "protocol_error", message: "Invalid bridge envelope." },
      });
      return;
    }
    if (message.type === "callback_result") {
      const waiter = pending.get(message.id);
      if (!waiter) return; // A timed-out/duplicate reply can never start or commit an operation.
      pending.delete(message.id);
      clearTimeout(waiter.timer);
      if (message.ok === true) waiter.resolve(message.value);
      else
        waiter.reject(
          record(message.error) && message.error.code === "not_applied"
            ? new EffectNotAppliedError("Backend certified no external effect.")
            : new Error("Backend callback failed."),
        );
      return;
    }
    const request = message;
    queue = queue.then(async () => {
      try {
        if (request.type !== "request") throw new Error("Invalid bridge request.");
        const value = await dispatch(request.method, request.params);
        write({ type: "result", id: request.id, ok: true, value });
      } catch (error) {
        const code =
          error instanceof EffectUncertainError
            ? "execution_uncertain"
            : error instanceof EffectNotAppliedError
              ? "not_applied"
              : "request_failed";
        write({
          type: "result",
          id: request.id,
          ok: false,
          error: {
            code,
            message: error instanceof Error ? error.message : "Backend operation failed.",
            ...(error instanceof EffectUncertainError ? { attemptId: error.attemptId } : {}),
          },
        });
      }
    });
  });
  await new Promise<void>((resolve) =>
    lines.once("close", () => {
      closed = true;
      for (const waiter of pending.values()) {
        clearTimeout(waiter.timer);
        waiter.reject(new Error("Backend pipe closed."));
      }
      pending.clear();
      resolve();
    }),
  );
  await queue;
}
