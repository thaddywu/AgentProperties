import { readdirSync, readFileSync } from "node:fs";
import type { Document } from "./translated-policy.js";

/** Read only the checked-in app description; never accept a browser-supplied filesystem path. */
export function novaDocuments(): Document[] {
  const root = new URL("../", import.meta.url);
  const names = [
    "app.md",
    "policy.md",
    "tools.md",
    ...readdirSync(new URL("agents/", root))
      .filter((name) => name.endsWith(".md"))
      .sort()
      .map((name) => `agents/${name}`),
  ];
  return names.map((path) => ({ path, content: readFileSync(new URL(path, root), "utf8") }));
}
