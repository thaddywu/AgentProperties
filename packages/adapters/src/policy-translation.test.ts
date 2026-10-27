import type { AgentRunRequest, AgentRuntime } from "@rakazo/adapter-kit";
import { describe, expect, it, vi } from "vitest";
import { policyTranslationModel } from "./policy-translation.js";

describe("one-shot policy model adapter", () => {
  it("uses one invocation with no tools and records the raw response", async () => {
    let request: AgentRunRequest | undefined;
    const run = vi.fn(async function* (input: AgentRunRequest) {
      request = input;
      yield { type: "text" as const, text: '{"policies":[]}' };
      yield { type: "done" as const, text: '{"policies":[]}' };
    });
    const record = vi.fn();
    const generate = policyTranslationModel(
      { run } as unknown as AgentRuntime,
      { provider: "offline-test", id: "fixture" },
      new AbortController().signal,
      "test instructions",
    );
    expect(await generate("test prompt", record)).toBe('{"policies":[]}');
    expect(run).toHaveBeenCalledTimes(1);
    expect(request?.tools).toEqual([]);
    expect(request?.useBuiltinTools).toBe(false);
    expect(record).toHaveBeenCalledWith('{"policies":[]}');
    await expect(request!.executeTool!("shell", {}, "test")).rejects.toThrow("no tools");
  });
  it("fails a transport error without exposing credentials and keeps partial text", async () => {
    const run = async function* () {
      yield { type: "text" as const, text: "partial output" };
      throw new Error("synthetic-secret-that-must-not-be-reported");
    };
    const record = vi.fn();
    const generate = policyTranslationModel(
      { run } as unknown as AgentRuntime,
      { provider: "offline-test", id: "fixture" },
      new AbortController().signal,
      "test instructions",
    );
    await expect(generate("prompt", record)).rejects.toThrow("Model invocation failed");
    expect(record).toHaveBeenCalledWith("partial output");
  });
});
