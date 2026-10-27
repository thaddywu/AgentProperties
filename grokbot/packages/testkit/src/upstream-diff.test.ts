import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const script = readFileSync(
  path.resolve(import.meta.dirname, "../../../scripts/upstream-diff.sh"),
  "utf8",
);
const fixtures: string[] = [];

afterEach(() => {
  for (const root of fixtures.splice(0)) rmSync(root, { recursive: true, force: true });
});

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "host-upstream-"));
  fixtures.push(root);
  const env = {
    ...process.env,
    GIT_AUTHOR_NAME: "Example",
    GIT_AUTHOR_EMAIL: "example@example.invalid",
    GIT_COMMITTER_NAME: "Example",
    GIT_COMMITTER_EMAIL: "example@example.invalid",
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
  };
  const git = (...args: string[]) =>
    execFileSync("git", args, { cwd: root, env, encoding: "utf8" }).trim();
  const write = (name: string, body: string) => {
    mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    writeFileSync(path.join(root, name), body);
  };
  const commit = () => {
    git("add", ".");
    git("-c", "commit.gpgsign=false", "commit", "-qm", "Example revision");
    return git("rev-parse", "HEAD");
  };
  git("init", "-q");
  write("apps/web/demo.txt", "old\n");
  write("package.json", '{"name":"before"}\n');
  const baseline = commit();
  write("apps/web/demo.txt", "new\n");
  write("package.json", '{"name":"after"}\n');
  const target = commit();
  write("grokbot/upstream-base", `${baseline}\n`);
  write("grokbot/scripts/upstream-diff.sh", script);
  const run = (...args: string[]) =>
    spawnSync("bash", ["grokbot/scripts/upstream-diff.sh", ...args], {
      cwd: root,
      env,
      encoding: "utf8",
    });
  return { root, git, baseline, target, run, write };
}

describe("upstream change export", () => {
  it("separates host and workspace changes without applying either", () => {
    const f = fixture();
    const result = f.run(f.target, "review with spaces");
    expect(result.status, result.stderr).toBe(0);
    const host = readFileSync(path.join(f.root, "review with spaces/host.patch"), "utf8");
    const workspace = readFileSync(
      path.join(f.root, "review with spaces/workspace-review.patch"),
      "utf8",
    );
    expect(host).toContain("a/apps/web/demo.txt");
    expect(host).not.toContain("a/package.json");
    expect(workspace).toContain("a/package.json");
    expect(workspace).not.toContain("a/apps/web/demo.txt");
    expect(f.git("diff", "--exit-code")).toBe("");
    expect(readFileSync(path.join(f.root, "grokbot/upstream-base"), "utf8")).toBe(
      `${f.baseline}\n`,
    );
    // Verify that the exported paths can be applied to the actual host prefix.
    f.write("grokbot/apps/web/demo.txt", "old\n");
    f.git("apply", "--check", "--directory=grokbot", "review with spaces/host.patch");
  });

  it("refuses to overwrite an existing export", () => {
    const f = fixture();
    f.write("review/keep.txt", "keep\n");
    expect(f.run(f.target, "review").status).not.toBe(0);
    expect(readFileSync(path.join(f.root, "review/keep.txt"), "utf8")).toBe("keep\n");
  });

  it("rejects a target older than the incorporated baseline", () => {
    const f = fixture();
    f.write("grokbot/upstream-base", `${f.target}\n`);
    const result = f.run(f.baseline, "review");
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("does not descend");
  });
});
