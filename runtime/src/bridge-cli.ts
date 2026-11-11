import { servePolicyBridge } from "./bridge.js";

await servePolicyBridge(process.stdin, process.stdout).catch(() => {
  process.stderr.write(
    "Policy bridge stopped after a transport failure. Reconcile uncertain effects before restarting.\n",
  );
  process.exitCode = 1;
});
