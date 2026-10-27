// Run repository-wide tools from the checkout root, using the host's installation.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const [tool, ...args] = process.argv.slice(2);
if (tool !== "tsx") throw new Error("Expected tsx");
const child = spawn(process.execPath, [require.resolve("tsx/cli"), ...args], {
  cwd: fileURLToPath(new URL("../../", import.meta.url)),
  stdio: "inherit",
});
const interrupt = () => child.kill("SIGINT");
const terminate = () => child.kill("SIGTERM");
process.on("SIGINT", interrupt);
process.on("SIGTERM", terminate);
child.on("error", (error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  process.off("SIGINT", interrupt);
  process.off("SIGTERM", terminate);
  if (signal) process.kill(process.pid, signal);
  else process.exitCode = code ?? 1;
});
