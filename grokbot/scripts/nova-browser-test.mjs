import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
// Override only for a preinstalled browser toolkit outside this checkout.
const { chromium } = process.env.NOVA_PLAYWRIGHT_MODULE
  ? await import(process.env.NOVA_PLAYWRIGHT_MODULE)
  : createRequire(new URL("../apps/web/package.json", import.meta.url))("@playwright/test");
const base = process.env.NOVA_URL ?? "http://127.0.0.1:5180";
const output = process.env.NOVA_SCREENSHOTS ?? "/tmp/nova-browser-review";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.NOVA_CHROMIUM ? { executablePath: process.env.NOVA_CHROMIUM } : {}), args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on("pageerror", e => errors.push(e.message));
const api = async body => {
  const response = await fetch(`${base}/nova-api`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json(); assert.equal(response.ok, true, JSON.stringify(data)); return data.result;
};
const current = () => api({ operation: "state" });
const reset = async preset => { const state = await current(); return api({ operation: "reset", preset, revision: state.version }); };
const clickRun = async name => {
  const operations = { "Run query": "query", PROOF: "why", "Run what-if": "what-if", "Find minimum": "minimal", "Find completion": "speculative", "Replay completion in runtime": "replay-trace", New: "reset", "Next event": "advance", Denial: "reset", "Apply configuration": "config", Send: "send" };
  assert.ok(operations[name], `Unknown test action: ${name}`);
  const response = page.waitForResponse(r => r.url().endsWith("/nova-api") && r.request().method() === "POST" && r.request().postDataJSON().operation === operations[name]);
  await page.getByRole("button", { name, exact: true }).click();
  const body = await (await response).json();
  await page.waitForTimeout(80);
  return body;
};
const selectSnapshot = async action => {
  const response = page.waitForResponse(r => r.url().endsWith("/nova-api") && r.request().method() === "POST" && r.request().postDataJSON().operation === "state");
  await action();
  const body = await (await response).json();
  assert.ok(body.result, JSON.stringify(body));
  await page.waitForTimeout(50);
};
try {
  await reset("denial");
  await page.goto(`${base}/nova.html`);
  await page.getByRole("tab", { name: "Query", exact: true }).waitFor();
  await page.getByRole("button", { name: "Questions", exact: true }).click();
  for (const category of ["Information flow", "Capability", "Communication", "Provenance", "Resource lifecycle"]) {
    await page.getByRole("tab", { name: category, exact: true }).click();
    assert.equal(await page.getByRole("dialog").getByRole("button", { name: /^Open question:/ }).count(), category === "Resource lifecycle" ? 0 : 3);
  }
  await page.screenshot({ path: `${output}/questions.png`, fullPage: true });
  await page.getByRole("tab", { name: "Capability", exact: true }).click();
  await page.getByRole("button", { name: "Open question: Which required permissions is this agent missing?", exact: true }).click();
  assert.equal(await page.getByLabel("Store scope").inputValue(), "auditor_b");
  const missing = await clickRun("Run query");
  assert.deepEqual(missing.result.rows, [["hr_review"]]);
  assert.equal(await page.getByRole("region", { name: "Audit report lifecycle" }).count(), 0);
  await page.getByRole("tab", { name: "Query", exact: true }).click();
  await page.getByLabel("Store scope").selectOption("auditor_a");
  console.log("PASS clear question templates and disconnected lifecycle catalog");
  await page.getByLabel("Datalog program").fill("?- Knows(auditor_a, Tag).");
  let result = await clickRun("Run query");
  assert.deepEqual(result.result.rows, [["nova_procurement"], ["nova_facility"]]);
  assert.equal(await page.getByRole("tabpanel", { name: "Query", exact: true }).getByText("What facts match this query?", { exact: true }).count(), 1);
  console.log("PASS terminal variable query");
  await page.getByLabel("Store scope").selectOption("auditor_b");
  result = await clickRun("Run query");
  assert.deepEqual(result.result.rows, []);
  await page.getByLabel("Store scope").selectOption("auditor_a");
  result = await clickRun("Run query");
  assert.equal(result.result.rows.length, 2);
  await page.getByRole("button", { name: "Protocol", exact: true }).click();
  await page.getByRole("heading", { name: "Local stores and transfers" }).waitFor();
  await page.screenshot({ path: `${output}/protocol.png`, fullPage: true });
  await page.keyboard.press("Escape");
  await page.getByLabel("Store scope").selectOption("debug");
  console.log("PASS local query isolation and protocol definition viewer");

  await page.getByRole("tab", { name: "Why", exact: true }).click();
  result = await clickRun("PROOF");
  assert.match(result.result.rule, /Knows\("auditor_a",T1\)/);
  assert.match(JSON.stringify(result.result), /TransportTag/);
  assert.match(result.result.fact, /DenyReceive/);
  await page.screenshot({ path: `${output}/why.png`, fullPage: true });
  console.log("PASS generated proof tree");

  const before = await current();
  await page.getByRole("tab", { name: "What-if", exact: true }).click();
  result = await clickRun("Run what-if");
  assert.equal(result.result.result, false);
  assert.deepEqual((await current()).records, before.records);
  await page.getByLabel("ADD", { exact: true }).fill("Finished(nova).");
  result = await clickRun("Run what-if");
  assert.match(result.error, /read-only/);
  await page.getByLabel("ADD", { exact: true }).fill("");
  console.log("PASS editable what-if, input isolation and derived-write rejection");

  await page.getByRole("tab", { name: "Min-prevention", exact: true }).click();
  result = await clickRun("Find minimum");
  assert.deepEqual(result.result.solutions, [["eP"], ["eF"]]);
  await page.getByLabel("PREVENTABLE EVENTS").fill("onlyFacility:\nReceiver(auditor_a, mF).\nReceived(auditor_a, mF).");
  result = await clickRun("Find minimum");
  assert.deepEqual(result.result.solutions, [["onlyFacility"]]);
  console.log("PASS editable minimal-prevention events");

  await page.getByRole("tab", { name: "Planning", exact: true }).click();
  result = await clickRun("Find completion");
  assert.equal(result.result.edges.find(e => e.action.id === "facility->auditor_a").classification, "dead-ending");
  assert.equal(result.result.edges.find(e => e.action.id === "facility->auditor_b").classification, "completion-preserving");
  await page.getByTestId("analysis-result").getByText("Completion exists", { exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${output}/speculative.png`, fullPage: true });
  await clickRun("Replay completion in runtime");
  assert.equal((await current()).finished, true);
  console.log("PASS speculative classifications and real completion replay");

  await clickRun("New");
  assert.equal((await current()).messages.length, 0);
  await clickRun("Next event");
  let state = await current();
  assert.equal(state.messages[0].status, "pending");
  assert.equal(state.records.some(r => r.fact.predicate === "Sender"), true);
  assert.equal(state.records.some(r => r.fact.predicate === "Received"), false);
  await clickRun("Next event");
  state = await current();
  assert.equal(state.messages[0].status, "delivered");
  assert.equal(state.records.some(r => r.fact.predicate === "Received"), true);
  console.log("PASS step-by-step runtime send and gate execution");

  await clickRun("Denial");
  await selectSnapshot(() => page.getByLabel("Store snapshot").selectOption("10"));
  await page.waitForTimeout(100);
  await selectSnapshot(() => page.getByRole("button", { name: "Before", exact: true }).click());
  await page.getByRole("tab", { name: "Query", exact: true }).click();
  await page.getByLabel("Datalog program").fill("?- Received(auditor_a, mF).");
  result = await clickRun("Run query");
  assert.deepEqual(result.result.rows, []);
  await selectSnapshot(() => page.getByRole("button", { name: "After", exact: true }).click());
  await page.waitForTimeout(100);
  result = await clickRun("Run query");
  assert.deepEqual(result.result.rows, [[]]);
  console.log("PASS historical before/after queries");

  await selectSnapshot(() => page.getByLabel("Store snapshot").selectOption("latest"));
  await page.waitForTimeout(100);
  await page.getByRole("button", { name: "Config", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "Application configuration", exact: true });
  await editor.fill((await editor.inputValue()).replace("HasCap(auditor_a, hr_review).", ""));
  await clickRun("Apply configuration");
  await page.getByRole("tab", { name: "Why", exact: true }).click();
  result = await clickRun("PROOF");
  assert.match(result.result.rule, /Requires/);
  console.log("PASS configuration changes actual derivations");

  await clickRun("Denial");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: `${output}/mobile.png`, fullPage: true });
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByLabel("Message body").fill("A real runtime message");
  await clickRun("Send");
  assert.equal((await current()).messages.at(-1).body, "A real runtime message");
  console.log("PASS narrow-screen inspector and real composer send");
  assert.deepEqual(errors, []);
  await reset("denial");
  console.log(`PASS browser suite · screenshots: ${output}`);
} finally { await browser.close(); }
