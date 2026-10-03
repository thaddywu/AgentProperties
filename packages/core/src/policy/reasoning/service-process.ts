import type { ChildProcess } from "node:child_process";
import { fork } from "node:child_process";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import type { RuntimeState } from "./runtime.js";
import type { Request } from "./service.js";

type Checkpoint = { state: RuntimeState; version: number };
/** Keep native evaluation off the HTTP event loop, with transactional timeout recovery. */
export class ServiceProcess {
  private child?: ChildProcess;
  private checkpoint?: Checkpoint;
  private busy = false;
  constructor(
    private worker: string,
    private stateFile?: string,
  ) {
    if (stateFile && existsSync(stateFile))
      this.checkpoint = JSON.parse(readFileSync(stateFile, "utf8"));
  }
  close() {
    const child = this.child;
    this.child = undefined;
    if (child?.pid) {
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch {
        child.kill("SIGKILL");
      }
    }
  }
  async run(request: Request): Promise<unknown> {
    if (this.busy)
      throw new Error(
        "An analysis is running. Please retry when it finishes (maximum 20 seconds).",
      );
    this.busy = true;
    try {
      if (!this.child)
        this.child = fork(this.worker, [], {
          execArgv: ["--import", "tsx"],
          detached: true,
          stdio: ["ignore", "inherit", "inherit", "ipc"],
        });
      const child = this.child;
      return await new Promise((resolve, reject) => {
        const cleanup = () => {
          clearTimeout(timer);
          child.off("message", message);
          child.off("error", failure);
          child.off("exit", exited);
        };
        const failure = (error: Error) => {
          cleanup();
          this.close();
          reject(error);
        };
        const exited = () =>
          failure(
            new Error(
              "Policy worker stopped. Retry; the last committed runtime state is preserved.",
            ),
          );
        const message = (reply: { result?: unknown; error?: string; checkpoint?: Checkpoint }) => {
          cleanup();
          if (reply.error) return reject(new Error(reply.error));
          try {
            if (reply.checkpoint) {
              if (this.stateFile) {
                writeFileSync(`${this.stateFile}.tmp`, JSON.stringify(reply.checkpoint));
                renameSync(`${this.stateFile}.tmp`, this.stateFile);
              }
              this.checkpoint = reply.checkpoint;
            }
            resolve(reply.result);
          } catch (error) {
            this.close();
            reject(error);
          }
        };
        const timer = setTimeout(
          () =>
            failure(
              new Error(
                "Analysis exceeded 20 seconds and was stopped. Runtime state was preserved; reduce the query or action set.",
              ),
            ),
          20_000,
        );
        child.once("message", message);
        child.once("error", failure);
        child.once("exit", exited);
        child.send({ request, checkpoint: this.checkpoint }, (error) => {
          if (error) failure(error);
        });
      });
    } finally {
      this.busy = false;
    }
  }
}
