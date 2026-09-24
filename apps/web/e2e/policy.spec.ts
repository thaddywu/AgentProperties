import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { advanceNova, messageFacts, NOVA_PHASES, newNovaSession } from "@rakazo/core";
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
  await denied.getByRole("button", { name: /Local store after event/ }).click();
  await expect(page.getByLabel("Snapshot principal")).toHaveValue("auditor_a");
  const store = page.getByTestId("policy-local-store");
  const after = await store.textContent();
  await page.getByRole("button", { name: "Before", exact: true }).click();
  expect(await store.textContent()).toBe(after);
  await expect(store).toContainText("Knows · 2");
  await captureScreenshot(page, testInfo, "native-policy-denied");
  await page.keyboard.press("Escape");
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await expect(page.getByTestId("policy-observation")).toHaveCount(0);
  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(denied).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await denied.getByRole("button", { name: /Local store after event/ }).click();
  await expect(page.getByLabel("Snapshot principal")).toBeVisible();
  await captureScreenshot(page, testInfo, "native-policy-mobile");
});
