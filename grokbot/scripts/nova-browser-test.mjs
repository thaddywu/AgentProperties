import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

// Override only for a preinstalled browser toolkit outside this checkout.
const { chromium } = process.env.NOVA_PLAYWRIGHT_MODULE
  ? await import(process.env.NOVA_PLAYWRIGHT_MODULE)
  : createRequire(new URL("../apps/web/package.json", import.meta.url))("@playwright/test");
const base = process.env.NOVA_URL ?? "http://127.0.0.1:5180";
const output = process.env.NOVA_SCREENSHOTS ?? "/tmp/nova-browser-review";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.NOVA_CHROMIUM ? { executablePath: process.env.NOVA_CHROMIUM } : {}),
  args: ["--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const api = async (body) => {
  const response = await fetch(`${base}/nova-api`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  assert.equal(response.ok, true, JSON.stringify(data));
  return data.result;
};
const current = () => api({ operation: "state" });
const reset = async (preset) => {
  const state = await current();
  return api({ operation: "reset", preset, revision: state.version });
};
const clickRun = async (name) => {
  const operations = {
    "Run query": "query",
    PROOF: "why",
    "Run what-if": "what-if",
    "Find minimum": "minimal",
    "Find completion": "speculative",
    "Replay completion in runtime": "replay-trace",
    New: "reset",
    "Next event": "advance",
    "Before third delivery": "reset",
    "Apply configuration": "config",
    Send: "send",
  };
  assert.ok(operations[name], `Unknown test action: ${name}`);
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/nova-api") &&
      r.request().method() === "POST" &&
      r.request().postDataJSON().operation === operations[name],
  );
  await page.getByRole("button", { name, exact: true }).click();
  const body = await (await response).json();
  await page.waitForTimeout(80);
  return body;
};
const selectSnapshot = async (action) => {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/nova-api") &&
      r.request().method() === "POST" &&
      r.request().postDataJSON().operation === "state",
  );
  await action();
  const body = await (await response).json();
  assert.ok(body.result, JSON.stringify(body));
  await page.waitForTimeout(50);
};
try {
  const initial = await current();
  if (initial.policyIdentity.mode !== "golden")
    await api({ operation: "start-policy", revision: initial.version });
  await reset("denial");
  await page.goto(`${base}/nova.html`);
  await page.getByRole("tab", { name: "Query", exact: true }).waitFor();
  await page.getByRole("button", { name: "Rules", exact: true }).click();
  await page.getByRole("heading", { name: "Rules and inputs", exact: true }).waitFor();
  const builtinPanel = page.getByRole("tabpanel", { name: "Runtime", exact: true });
  assert.match(await builtinPanel.innerText(), /TransportTag\(Message, Tag\)/);
  assert.match(await builtinPanel.innerText(), /capability/);
  assert.doesNotMatch(await builtinPanel.innerText(), /three-tag-exposure|AuditGoal/);
  await builtinPanel.getByText("Built-in protocol", { exact: true }).click();
  await builtinPanel.getByRole("table").waitFor();
  assert.match(await builtinPanel.innerText(), /MessageTag → TransportTag/);
  assert.match(await builtinPanel.innerText(), /Keep on allow; discard on deny/);
  assert.doesNotMatch(await builtinPanel.innerText(), /"replicated"\s*:/);
  await page.screenshot({ path: `${output}/builtin-protocol-table.png`, fullPage: true });
  await builtinPanel.getByText("Built-in protocol", { exact: true }).click();
  await builtinPanel.getByText("App-supplied values", { exact: true }).click();
  assert.match(await builtinPanel.innerText(), /HasCap\(auditor_a, hr_review\)/);
  await page.screenshot({ path: `${output}/builtin-policy.png`, fullPage: true });
  await page.getByRole("tab", { name: "Reference", exact: true }).click();
  const novaPanel = page.getByRole("tabpanel", { name: "Reference", exact: true });
  assert.match(await novaPanel.innerText(), /Handwritten Nova rules/);
  assert.match(await novaPanel.innerText(), /three-tag-exposure/);
  assert.match(await novaPanel.innerText(), /AuditGoal\(Group, Tag1, Tag2, Tag3\)/);
  assert.doesNotMatch(await novaPanel.innerText(), /runtime-dependency/);
  await novaPanel.getByText("Nova protocol", { exact: true }).click();
  assert.match(await novaPanel.innerText(), /Global query only: Finished/);
  assert.doesNotMatch(await novaPanel.innerText(), /AuditReceipt/);
  assert.match(await novaPanel.innerText(), /Only at board/);
  await novaPanel.getByText("Nova protocol", { exact: true }).click();
  await page.screenshot({ path: `${output}/nova-policy.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
  );
  // Measure in one frame: the dialog can still be moving after a viewport resize.
  assert.ok(
    await page.getByRole("tablist", { name: "Policy walkthrough" }).evaluate((list) => {
      const bounds = list.getBoundingClientRect();
      const last = list.lastElementChild.getBoundingClientRect();
      return last.bottom <= bounds.bottom + 1;
    }),
  );
  await page.screenshot({ path: `${output}/nova-policy-narrow.png`, fullPage: true });
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.getByRole("tab", { name: "Nova input", exact: true }).click();
  await page.getByText("policy.md", { exact: true }).click();
  assert.match(
    await page.getByRole("tabpanel", { name: "Nova input", exact: true }).innerText(),
    /P3\. No agent other than Board/,
  );
  await page.getByRole("tab", { name: "Translated", exact: true }).click();
  await page.getByLabel("Import translation artifact").waitFor();
  assert.match(
    await page.getByRole("tabpanel", { name: "Translated", exact: true }).innerText(),
    /one-shot extension command/,
  );
  await page.getByRole("tab", { name: "Prevention", exact: true }).click();
  await page.getByRole("button", { name: "Check closure union", exact: true }).click();
  await page
    .getByText(
      "Local closure union, global completion and pending gate decisions match full-copy.",
      { exact: true },
    )
    .waitFor();
  await page.getByRole("button", { name: "Run prevention comparison", exact: true }).click();
  await page.getByRole("heading", { name: "Third distinct tag", exact: true }).waitFor();
  assert.match(
    await page.getByRole("tabpanel", { name: "Prevention", exact: true }).innerText(),
    /Reference: passed/,
  );
  await page.screenshot({ path: `${output}/policy-prevention.png`, fullPage: true });
  const fixture = execFileSync(process.execPath, [
    "--import",
    createRequire(new URL("../../apps/nova/package.json", import.meta.url)).resolve("tsx"),
    fileURLToPath(new URL("../../apps/nova/tests/browser-policy-fixture.ts", import.meta.url)),
  ]);
  await page.getByRole("tab", { name: "Translated", exact: true }).click();
  await page
    .getByLabel("Import translation artifact")
    .setInputFiles({ name: "nova-policy.json", mimeType: "application/json", buffer: fixture });
  await page
    .getByText("Checks passed; semantic equivalence is unproven.", { exact: true })
    .waitFor();
  await page.screenshot({ path: `${output}/translated-policy.png`, fullPage: true });
  await selectSnapshot(async () => {
    await page.getByRole("button", { name: "Start translated session", exact: true }).click();
    await page.getByText(/^Active: Translated/).waitFor();
  });
  const active = await current();
  assert.equal(active.policyIdentity.mode, "translated");
  await api({ operation: "reset", preset: "denial", revision: active.version });
  const pendingState = await current();
  const deniedState = await api({ operation: "settle", id: "mH", revision: pendingState.version });
  assert.equal(deniedState.messages.find((message) => message.id === "mH").status, "denied");
  assert.equal(
    deniedState.records.some(
      (record) => record.fact.predicate === "Received" && record.fact.args[1] === "mH",
    ),
    false,
  );
  await page.reload();
  await page.getByRole("button", { name: "Rules", exact: true }).click();
  await page.getByText(/^Active: Translated/).waitFor();
  await page.getByRole("tab", { name: "Reference", exact: true }).click();
  await selectSnapshot(async () => {
    await page.getByRole("button", { name: "Start reference session", exact: true }).click();
    await page.getByText(/^Active: Reference/).waitFor();
  });
  await page.keyboard.press("Escape");
  await reset("denial");
  await page.reload();
  await page.getByRole("tab", { name: "Query", exact: true }).waitFor();
  const replayBefore = await current();
  await page.getByRole("button", { name: "View historical translation", exact: true }).click();
  await page.getByRole("region", { name: "Policy comparison" }).waitFor();
  await page
    .getByText(
      "Historical protocol: saved results only. Cannot run or activate in the current runtime.",
      { exact: true },
    )
    .waitFor();
  const comparison = page.getByRole("region", { name: "Policy comparison" });
  await page.getByText("Exact translation input", { exact: true }).click();
  const sourceDocuments = page.getByText("Exact translation input", { exact: true }).locator("..");
  await sourceDocuments.getByText("policy.md", { exact: true }).click();
  assert.match(await sourceDocuments.innerText(), /P3\. No agent other than Board/);
  assert.doesNotMatch(await sourceDocuments.innerText(), /"content"\s*:/);
  await page.getByText("Exact translation input", { exact: true }).click();
  assert.match(await comparison.innerText(), /P3\. No agent other than Board/);
  const gtBounds = await page.getByRole("region", { name: "Reference rules" }).boundingBox();
  const generatedBounds = await page.getByRole("region", { name: "Generated rules" }).boundingBox();
  assert.ok(generatedBounds.x > gtBounds.x && Math.abs(generatedBounds.y - gtBounds.y) < 2);
  await page.screenshot({ path: `${output}/translation-side-by-side.png`, fullPage: true });
  await page.getByLabel("Compare policy").selectOption("P5");
  assert.match(
    await page.getByRole("region", { name: "Reference rules" }).innerText(),
    /Audited\(Tag\) :- AuditReceipt/,
  );
  assert.doesNotMatch(
    await page.getByRole("region", { name: "Generated rules" }).innerText(),
    /Audited\(Tag\) :- AuditReceipt/,
  );
  await page.screenshot({ path: `${output}/translation-audit-difference.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
  );
  await page.screenshot({ path: `${output}/translation-comparison-narrow.png`, fullPage: true });
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.getByRole("tab", { name: "Prevention", exact: true }).click();
  await page.getByRole("button", { name: "Run prevention comparison", exact: true }).click();
  await page.getByRole("heading", { name: "Split audit completion", exact: true }).waitFor();
  const auditCase = page
    .getByRole("heading", { name: "Split audit completion", exact: true })
    .locator("..");
  assert.match(await auditCase.innerText(), /Reference: passed/);
  assert.doesNotMatch(
    await page.getByRole("tabpanel", { name: "Prevention", exact: true }).innerText(),
    /role changes|historical receipts/,
  );
  await auditCase.getByText("Delivery and payload evidence", { exact: true }).click();
  assert.match(await auditCase.innerText(), /Content visible to recipient/);
  assert.doesNotMatch(await auditCase.innerText(), /"bodyVisible"\s*:/);
  await page.screenshot({ path: `${output}/prevention-readable-evidence.png`, fullPage: true });
  const replayAfter = await current();
  assert.equal(replayAfter.version, replayBefore.version);
  assert.deepEqual(replayAfter.messages, replayBefore.messages);
  await page.keyboard.press("Escape");
  console.log(
    "PASS saved translation replay, policy correspondence, side-by-side rules and unchanged runtime",
  );
  console.log(
    "PASS five-part policy walkthrough, input documents, closure union and actual prevention",
  );
  await page.getByRole("button", { name: "Questions", exact: true }).click();
  for (const category of ["Information flow", "Capability", "Communication", "Provenance"]) {
    await page.getByRole("tab", { name: category, exact: true }).click();
    assert.equal(
      await page
        .getByRole("dialog")
        .getByRole("button", { name: /^Open question:/ })
        .count(),
      category === "Communication" ? 5 : 3,
    );
  }
  await page.screenshot({ path: `${output}/questions.png`, fullPage: true });
  await page.getByRole("tab", { name: "Capability", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Open question: Which permission is Auditor B missing for HR information?",
      exact: true,
    })
    .click();
  await page.getByRole("dialog", { name: "Questions", exact: true }).waitFor({ state: "hidden" });
  assert.equal(await page.getByLabel("Store scope").inputValue(), "auditor_b");
  const missing = await clickRun("Run query");
  assert.deepEqual(missing.result.rows, [["hr_review"]]);
  assert.equal(await page.getByRole("region", { name: "Audit report lifecycle" }).count(), 0);
  await page.getByRole("tab", { name: "Query", exact: true }).click();
  await page.getByLabel("Store scope").selectOption("auditor_a");
  console.log("PASS concrete question examples and offline interpretation");
  await page.getByRole("button", { name: "Questions", exact: true }).click();
  await page.getByRole("tab", { name: "Information flow", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Open question: Who has already received HR information?",
      exact: true,
    })
    .click();
  await page.getByRole("dialog", { name: "Questions", exact: true }).waitFor({ state: "hidden" });
  assert.equal(await page.getByLabel("Store scope").inputValue(), "debug");
  assert.match(
    await page.getByRole("region", { name: "Datalog analysis terminal" }).innerText(),
    /Who has already received HR information/,
  );
  const interpreted = await clickRun("Run query");
  assert.deepEqual(interpreted.result.rows, [["hr"]]);
  await page.screenshot({ path: `${output}/nl-query.png`, fullPage: true });
  // Deterministic UI fixture: server model interpretation is tested separately with an injected provider.
  await page.route("**/nova-question", async (route) => {
    const request = route.request().postDataJSON();
    const result =
      request.question === "Why was it blocked?"
        ? { status: "needs_clarification", message: "Which message and recipient?" }
        : {
            status: "ready",
            revision: request.revision,
            selection: {},
            question: {
              id: "denial",
              category: "Communication",
              template: "WHY DenyReceive({recipient}, {message})",
              question: "Why would message mH to Auditor A be blocked?",
              originalQuestion: request.question,
              interpretationSource: "model",
              tab: "why",
              scope: "auditor_a",
              query: 'DenyReceive("auditor_a", "mH")',
            },
          };
    assert.equal(request.mode, "model");
    if (result.status === "ready") {
      if (request.question.startsWith("If Auditor A"))
        Object.assign(result.question, {
          id: "without-receive",
          tab: "what-if",
          question: "Would HR still be blocked without the Facility receipt?",
          parameters: { recipient: "auditor_a", message: "mH", earlierMessage: "mF" },
          remove: 'Received("auditor_a", "mF").',
          add: "",
          argumentNotes: [
            "ADD is empty: this template changes only the specified earlier receipt.",
          ],
        });
      if (request.question.startsWith("Among Auditor A"))
        Object.assign(result.question, {
          id: "prevention",
          tab: "minimal",
          question: "Which of mP and mF should be prevented?",
          parameters: { recipient: "auditor_a", message: "mH", eventMessages: ["mP", "mF"] },
          events:
            'event1:\n  Received("auditor_a", "mP").\nevent2:\n  Received("auditor_a", "mF").',
        });
      if (request.question.startsWith("Starting when Auditor A"))
        Object.assign(result.question, {
          id: "planning",
          tab: "speculative",
          scope: "debug",
          question: "How can we finish Nova from before the second delivery?",
          parameters: {
            goalGroup: "nova",
            basis: "earlier",
            routes: [
              "facility->auditor_a",
              "facility->auditor_b",
              "hr->auditor_a",
              "hr->auditor_b",
            ],
          },
          goal: 'Finished("nova")',
          basis: "earlier",
          actions: "facility->auditor_a\nfacility->auditor_b\nhr->auditor_a\nhr->auditor_b",
        });
    }
    await route.fulfill({ json: { result } });
  });
  const beforeInterpretation = await current();
  await page.getByRole("button", { name: "Questions", exact: true }).click();
  await page.getByLabel("Ask about Nova").fill("Why was it blocked?");
  await page.getByRole("button", { name: "Interpret question", exact: true }).click();
  await page.getByText("Which message and recipient?", { exact: true }).waitFor();
  await page.getByLabel("Ask about Nova").fill("Why can't A receive the HR message mH?");
  await page.getByRole("button", { name: "Interpret question", exact: true }).click();
  await page.getByRole("dialog", { name: "Questions", exact: true }).waitFor({ state: "hidden" });
  assert.equal(await page.getByLabel("Store scope").inputValue(), "auditor_a");
  assert.match(
    await page.getByRole("region", { name: "Datalog analysis terminal" }).innerText(),
    /Model interpretation/,
  );
  assert.equal((await current()).version, beforeInterpretation.version);
  const nlProof = await clickRun("PROOF");
  assert.match(nlProof.result.fact, /DenyReceive/);
  await page.screenshot({ path: `${output}/nl-query-interpreted.png`, fullPage: true });
  for (const label of ["What-if", "Min-prevention", "Planning"]) {
    await page.getByRole("button", { name: "Questions", exact: true }).click();
    await page.getByRole("button", { name: `Use ${label} question`, exact: true }).click();
    assert.ok((await page.getByLabel("Ask about Nova").inputValue()).length > 30);
    await page.screenshot({ path: `${output}/suggested-${label}.png`, fullPage: true });
    await page.getByRole("button", { name: "Interpret question", exact: true }).click();
    await page.getByRole("dialog", { name: "Questions", exact: true }).waitFor({ state: "hidden" });
    await page.getByText("Interpreted arguments", { exact: true }).click();
    if (label === "What-if") {
      assert.equal(
        await page.getByLabel("REMOVE", { exact: true }).inputValue(),
        'Received("auditor_a", "mF").',
      );
      assert.equal(await page.getByLabel("ADD", { exact: true }).inputValue(), "");
      assert.equal((await clickRun("Run what-if")).result.result, false);
    } else if (label === "Min-prevention") {
      assert.match(await page.getByLabel("PREVENTABLE EVENTS").inputValue(), /event1:/);
      assert.deepEqual((await clickRun("Find minimum")).result.solutions, [["event1"], ["event2"]]);
    } else {
      assert.equal(await page.getByLabel("GOAL", { exact: true }).inputValue(), 'Finished("nova")');
      assert.equal((await page.getByLabel("PROGRESS ACTIONS").inputValue()).split("\n").length, 4);
      assert.equal(await page.getByLabel("Speculative starting state").inputValue(), "earlier");
      assert.ok((await clickRun("Find completion")).result.trace.length);
    }
    await page.screenshot({ path: `${output}/arguments-${label}.png`, fullPage: true });
  }
  await page.unroute("**/nova-question");
  console.log("PASS synthetic model interpretation UI, clarification and explicit query execution");
  await page.getByRole("tab", { name: "Query", exact: true }).click();
  await page.getByLabel("Store scope").selectOption("auditor_a");
  await page.getByLabel("Datalog program").fill("?- HasReceivedTag(auditor_a, Tag).");
  let result = await clickRun("Run query");
  assert.deepEqual(result.result.rows, [["nova_procurement"], ["nova_facility"]]);
  assert.equal(
    await page
      .getByRole("tabpanel", { name: "Query", exact: true })
      .getByText("What facts match this query?", { exact: true })
      .count(),
    1,
  );
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
  assert.match(result.result.rule, /HasReceivedTag\("auditor_a",T1\)/);
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
  await page
    .getByLabel("PREVENTABLE EVENTS")
    .fill("eP:\nReceived(auditor_a, mP).\neF:\nReceived(auditor_a, mF).");
  result = await clickRun("Find minimum");
  assert.deepEqual(result.result.solutions, [["eP"], ["eF"]]);
  await page.getByLabel("PREVENTABLE EVENTS").fill("onlyFacility:\nReceived(auditor_a, mF).");
  result = await clickRun("Find minimum");
  assert.deepEqual(result.result.solutions, [["onlyFacility"]]);
  console.log("PASS editable minimal-prevention events");

  await page.getByRole("tab", { name: "Planning", exact: true }).click();
  result = await clickRun("Find completion");
  assert.equal(
    result.result.edges.find((e) => e.action.id === "facility->auditor_a").classification,
    "dead-ending",
  );
  assert.equal(
    result.result.edges.find((e) => e.action.id === "facility->auditor_b").classification,
    "completion-preserving",
  );
  await page
    .getByTestId("analysis-result")
    .getByText("Completion exists", { exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${output}/speculative.png`, fullPage: true });
  await clickRun("Replay completion in runtime");
  assert.equal((await current()).finished, true);
  console.log("PASS speculative classifications and real completion replay");

  await clickRun("New");
  assert.equal((await current()).messages.length, 0);
  await clickRun("Next event");
  let state = await current();
  assert.equal(state.messages[0].status, "pending");
  assert.equal(
    state.records.some((r) => r.fact.predicate === "Sender"),
    true,
  );
  assert.equal(
    state.records.some((r) => r.fact.predicate === "Received"),
    false,
  );
  await clickRun("Next event");
  state = await current();
  assert.equal(state.messages[0].status, "delivered");
  assert.equal(
    state.records.some((r) => r.fact.predicate === "Received"),
    true,
  );
  console.log("PASS step-by-step runtime send and gate execution");

  await clickRun("Before third delivery");
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

  await clickRun("Before third delivery");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
  );
  await page.screenshot({ path: `${output}/mobile.png`, fullPage: true });
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByLabel("Message body").fill("A real runtime message");
  await clickRun("Send");
  assert.equal((await current()).messages.at(-1).body, "A real runtime message");
  console.log("PASS narrow-screen inspector and real composer send");
  assert.deepEqual(errors, []);
  await reset("denial");
  console.log(`PASS browser suite · screenshots: ${output}`);
} finally {
  await browser.close();
}
