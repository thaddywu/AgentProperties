import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import {
  advanceNova,
  messageFacts,
  NOVA_PHASES,
  newNovaSession,
  queryPolicyStores,
} from "@rakazo/core";
import { captureScreenshot, completeOnboarding, signup } from "./helpers";

test("native chat exposes policy tags and event snapshots without replacing its view", async ({
  page,
}, testInfo) => {
  const authFile = process.env.POLICY_E2E_AUTH_FILE;
  if (authFile) {
    const response = await page.request.post("/api/auth/sign-in/email", {
      data: JSON.parse(readFileSync(authFile, "utf8")),
      headers: { Origin: new URL(testInfo.project.use.baseURL!).origin },
    });
    expect(response.ok()).toBe(true);
    await page.goto("/app");
  } else {
    await signup(page, `native-policy-${Date.now()}@rakazo.test`, "password12", "Policy observer");
    await completeOnboarding(page);
  }
  const response = await page.request.post("/rpc/policyNative/enable", { data: { json: {} } });
  expect(response.ok()).toBe(true);
  const context = (await response.json()).json;
  const live = process.env.POLICY_E2E_LIVE === "1";
  if (!live) {
    const state = newNovaSession();
    for (let i = 0; i < NOVA_PHASES.length; i++)
      await advanceNova(state, async () => ({ text: "Budget-only reply", model: "offline" }));
    const event = state.events.find((e) => e.decision === "deny")!;
    await page.route(/\/rpc\/policyNative\/inspect$/, (route) =>
      route.fulfill({ json: { json: { id: "fixture", revision: 1, state } } }),
    );
    await page.route(/\/rpc\/policyNative\/query$/, async (route) => {
      const input = route.request().postDataJSON().json;
      const selected = state.events.find((e) => e.seq === input.event);
      const stores = selected ? selected[input.side as "before" | "after"] : state.local;
      await route.fulfill({
        json: { json: queryPolicyStores(stores, input.scope, input.program) },
      });
    });
    await page.route(/\/rpc\/(threads\/get|bootstrap)$/, async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      const snapshot = body.json.thread ?? body.json;
      snapshot.messages = [
        {
          id: "policy-fixture",
          threadId: snapshot.threadId,
          seq: 0,
          role: "bot",
          botId: context.bots.hiring,
          blocks: [{ kind: "meta", text: "message_bot → Auditor A · Denied (R3c)" }],
          createdAt: new Date().toISOString(),
          policy: {
            sessionId: "fixture",
            event,
            facts: messageFacts(state.artifacts[event.artifactId]!),
            artifacts: state.artifacts,
          },
        },
      ];
      await route.fulfill({ response: res, json: body });
    });
  }
  let inspectedBot = context.bots.hiring;
  if (live) {
    await expect
      .poll(
        async () => {
          for (const principal of ["procurement", "facility", "hiring"]) {
            const response = await page.request.post("/rpc/threads/messages", {
              headers: { "x-rakazo-space-id": context.policySpaceId },
              data: { json: { botId: context.bots[principal], includePeerRuns: true } },
            });
            const body = (await response.json()).json;
            if (body?.messages?.some((m: any) => m.policy?.event?.decision === "deny")) {
              inspectedBot = context.bots[principal];
              return true;
            }
          }
          return false;
        },
        { timeout: 90000 },
      )
      .toBe(true);
  }
  await page.evaluate(
    (spaceId) => localStorage.setItem("rakazo:space-id", spaceId),
    context.policySpaceId,
  );
  await page.goto(`/app/${inspectedBot}`);
  const toggle = page.getByRole("switch", { name: "Use Our Policy" });
  await expect(toggle).toBeChecked();
  await expect(page.getByTestId("policy-console")).toHaveCount(0);
  const denied = page.locator("[data-message-id]").filter({ hasText: "Denied (R3c)" });
  await expect(denied).toHaveCount(1);
  await denied.hover();
  await expect(denied.getByTestId("policy-hover-tags")).toContainText("Carries(");
  await expect(page.getByRole("button", { name: /Local store after event/ })).toHaveCount(0);
  await page.getByLabel("Store scope").selectOption("auditor_a");
  const deniedEvent = await page
    .getByLabel("Store snapshot")
    .locator("option")
    .filter({ hasText: /receive.*Denied/ })
    .first()
    .getAttribute("value");
  await page.getByLabel("Store snapshot").selectOption(deniedEvent!);
  await expect(page.getByLabel("Store scope")).toHaveValue("auditor_a");
  const store = page.getByTestId("inspector-facts");
  const after = await store.textContent();
  await page.getByRole("button", { name: "Before", exact: true }).click();
  expect(await store.textContent()).toBe(after);
  await expect(store).toContainText("Knows · 2");
  await captureScreenshot(page, testInfo, "native-policy-denied");
  await page
    .getByLabel("Datalog program")
    .fill("KnownPart(C) :- Knows(auditor_a, P, C).\n?- KnownPart(C).");
  await page.getByRole("button", { name: "Run query", exact: true }).click();
  const terminal = page.getByRole("region", { name: "Datalog Query" });
  await expect(terminal).toContainText("2 result(s)");
  await page.getByLabel("Store scope").selectOption("global");
  await page.getByLabel("Datalog program").fill("?- Store_Knows(Owner, A, P, C).");
  await page.getByRole("button", { name: "Run query", exact: true }).click();
  await expect(terminal.locator("table").first()).toContainText("procurement");
  await captureScreenshot(page, testInfo, "native-policy-inspector-query");
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await expect(page.getByTestId("policy-observation")).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "Store Inspector" })).toHaveCount(0);
  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(denied).toHaveCount(1);
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Stores", exact: true }).click();
  await page.getByLabel("Store scope").selectOption("auditor_a");
  await page.getByLabel("Store snapshot").selectOption(deniedEvent!);
  await expect(page.getByLabel("Store scope")).toBeVisible();
  await captureScreenshot(page, testInfo, "native-policy-mobile");
});
