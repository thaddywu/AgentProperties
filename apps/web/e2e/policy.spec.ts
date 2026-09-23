import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { advanceNova, NOVA_PHASES, newNovaSession } from "@rakazo/core";
import { captureScreenshot, completeOnboarding, signup } from "./helpers";

test("policy facts, historical stores, denial and original mode remain independent", async ({
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
    await signup(page, `policy-${Date.now()}@rakazo.test`, "password12", "Policy Observer");
    await completeOnboarding(page);
  }
  // Deterministic UI fixture uses the actual protocol; the live canary reads the saved backend episode.
  const state = newNovaSession();
  for (let i = 0; i < NOVA_PHASES.length; i++) {
    await advanceNova(state, async () => ({ text: "Budget reply fixture", model: "offline" }));
  }
  if (process.env.POLICY_E2E_LIVE !== "1") {
    await page.route("**/rpc/policySessions/get", (route) =>
      route.fulfill({
        json: { json: { id: "policy-fixture", revision: 11, state } },
      }),
    );
  }
  const toggle = page.getByRole("switch", { name: "Use Our Policy" });
  await expect(toggle).toBeVisible();
  if ((await toggle.getAttribute("aria-checked")) === "true") await toggle.click();
  await expect(page.getByTestId("policy-console")).not.toBeVisible();
  await toggle.click();
  await expect(page.getByText("Audit incomplete — policy enforced")).toBeVisible();
  const denied = page.locator(".policy-denied");
  await expect(denied).toHaveCount(1);
  await expect(denied).toContainText("msg_hiring_to_auditor_a_2");
  await expect(denied).toContainText("Carries(reply_hiring, nova, hiring)");
  await denied.getByRole("button").click();
  await expect(page.getByTestId("policy-decision")).toContainText("R3c");
  const facts = page.getByTestId("local-facts");
  const after = await facts.textContent();
  await page.getByRole("button", { name: "Before", exact: true }).click();
  expect(await facts.textContent()).toBe(after);
  await expect(facts).not.toContainText("Received(auditor_a, reply_hiring)");
  await expect(facts).toContainText("Knows(auditor_a, nova, procurement)");
  await captureScreenshot(page, testInfo, "policy-denied-receive");
  await toggle.click();
  await expect(page.getByTestId("policy-console")).not.toBeVisible();
  await expect(page.getByText("Local store", { exact: true })).not.toBeVisible();
  await toggle.click();
  await expect(page.getByTestId("policy-decision")).toContainText("R3c");
  expect(await facts.textContent()).toBe(after);
  await page.getByRole("button", { name: "Protocol & rules" }).click();
  await expect(page.getByRole("dialog")).toContainText("DerivedFrom");
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open local store" }).click();
  await expect(page.getByRole("combobox", { name: "Principal" })).toBeVisible();
  await captureScreenshot(page, testInfo, "policy-mobile-store");
});
