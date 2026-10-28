import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

export type ApplicationDocuments = { path: string; content: string }[];
export type NaturalLanguagePolicy = { id: string; text: string };

export function extractPolicies(source: string): NaturalLanguagePolicy[] {
  const policies = source
    .trim()
    .split(/\r?\n\s*\r?\n/)
    .filter((part) => !part.startsWith("#"))
    .map((part, index) => {
      const match = /^P([1-9]\d*)\.\s+([\s\S]+)$/.exec(part);
      if (!match || Number(match[1]) !== index + 1 || /\nP\d+\./.test(match[2]!))
        throw new Error(
          "Policies must be separate paragraphs numbered consecutively P1., P2., ...",
        );
      return { id: `P${match[1]}`, text: match[2]!.trim() };
    });
  if (!policies.length) throw new Error("policy.md contains no numbered policies.");
  return policies;
}

export async function loadApplication(directory: string): Promise<ApplicationDocuments> {
  const files = ["app.md", "policy.md", "tools.md"];
  for (const folder of ["agents", "episodes"]) {
    const entries = await readdir(join(directory, folder), { withFileTypes: true }).catch(
      (error) => {
        if (folder === "episodes" && error.code === "ENOENT") return [];
        throw new Error(`Cannot read ${folder}/.`);
      },
    );
    const markdown = entries.filter((entry) => entry.isFile() && entry.name.endsWith(".md"));
    if (folder === "agents" && !markdown.length) throw new Error("agents/ must contain Markdown.");
    files.push(...markdown.map((entry) => `${folder}/${entry.name}`).sort());
  }
  const documents: ApplicationDocuments = [];
  let size = 0;
  for (const path of files) {
    const content = await readFile(join(directory, path), "utf8").catch(() => {
      throw new Error(`Cannot read required application document: ${path}`);
    });
    size += Buffer.byteLength(content);
    if (!content.trim() || size > 128_000)
      throw new Error("Empty document or application exceeds 128 KB.");
    documents.push({ path, content });
  }
  extractPolicies(documents.find((doc) => doc.path === "policy.md")!.content);
  return documents;
}
