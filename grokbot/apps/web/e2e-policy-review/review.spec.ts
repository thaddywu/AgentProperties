import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("reviews a mapped behavior, saves feedback, exposes gaps and exports the exact review", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/policy-review.html");
  await expect(page.getByRole("heading", { name: "Does this match your policy?" })).toBeVisible();
  await expect(page.getByText("Reference reading · hand-authored")).toBeVisible();
  await page.getByRole("button", { name: "P3 Evidence for job decisions", exact: true }).click();
  await page.getByRole("button", { name: /^Before marking a job COMPLETED/ }).click();
  await expect(page.getByTestId("behavior-summary")).toContainText("ended successfully");
  await expect(page.getByText(/exit_code = 0/)).not.toBeVisible();
  await page
    .getByRole("group", { name: "Your expected behavior" })
    .getByRole("button", { name: "Yes", exact: true })
    .click();
  await page.getByRole("button", { name: "Different", exact: true }).click();
  await page.getByRole("button", { name: "Too restrictive", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Review note" })
    .fill("A failed run has still ended; success should be a separate status.");
  await page.screenshot({ path: testInfo.outputPath("policy-review.png"), fullPage: true });
  await page.getByRole("button", { name: "Switch to dark mode", exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath("policy-review-dark.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Switch to light mode", exact: true }).click();
  await page.getByText("Conditions & evidence", { exact: true }).click();
  await expect(page.getByText(/exit_code = 0/)).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("policy-review-evidence.png"),
    fullPage: true,
  });

  await page.reload();
  await page.getByRole("button", { name: "P3 Evidence for job decisions", exact: true }).click();
  await page.getByRole("button", { name: /^Before marking a job COMPLETED/ }).click();
  await expect(page.getByRole("textbox", { name: "Review note" })).toHaveValue(/A failed run/);
  await expect(page.getByRole("button", { name: "Different", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export review", exact: true }).click();
  const report = JSON.parse(await readFile((await (await download).path())!, "utf8"));
  expect(report.review.origin).toBe("reference");
  expect(report.feedback.completion).toMatchObject({
    rating: "different",
    difference: "stricter",
    expectation: "yes",
  });
  expect(report.review.rules.length).toBeGreaterThan(0);

  await page
    .getByRole("button", { name: "P2 Information flow and isolation", exact: true })
    .click();
  await page.getByRole("checkbox", { name: "Unmapped", exact: true }).check();
  await expect(page.getByTestId("behavior-summary")).toContainText("Prevent peer disclosure");
  await page.getByText("What is missing", { exact: true }).click();
  await expect(page.getByRole("region", { name: "Policy interpretation" })).toContainText(
    "not fully mediated",
  );
  await page.screenshot({
    path: testInfo.outputPath("policy-review-unmapped.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true);
  await page.screenshot({ path: testInfo.outputPath("policy-review-mobile.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("keeps edited text after a missing model error and never disguises the reference as a new translation", async ({
  page,
  request,
}) => {
  await page.goto("/policy-review.html");
  await page.getByRole("button", { name: "Edit policy", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Policy text" })
    .fill("P1. Students may only read their own jobs.");
  await page.getByRole("button", { name: "Translate", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Connect a model");
  await expect(page.getByRole("textbox", { name: "Policy text" })).toHaveValue(
    "P1. Students may only read their own jobs.",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByText("Reference reading · hand-authored")).toBeVisible();
  const rejected = await request.post("/policy-review-api", {
    headers: { Origin: "https://untrusted.example" },
    data: { operation: "load" },
  });
  expect(rejected.status()).toBe(400);
});

test("restores a model draft and its feedback with an explicit model-response fixture", async ({
  page,
  request,
}) => {
  const response = await request.post("/policy-review-api", { data: { operation: "load" } });
  const workspace = (await response.json()).result;
  const modelFixture = {
    ...workspace,
    modelAvailable: true,
    review: { ...workspace.review, id: "a".repeat(64), origin: "model" },
  };
  await page.route("**/policy-review-api", async (route) => {
    if (route.request().postDataJSON()?.operation === "translate")
      await route.fulfill({ json: { result: modelFixture } });
    else await route.continue();
  });
  await page.goto("/policy-review.html");
  await page.getByRole("button", { name: "Edit policy", exact: true }).click();
  await page.getByRole("button", { name: "Translate", exact: true }).click();
  await expect(page.getByText("Model translation · draft")).toBeVisible();
  await page.getByRole("button", { name: "Matches", exact: true }).click();
  await page.reload();
  await expect(page.getByText("Model translation · draft")).toBeVisible();
  await expect(page.getByRole("button", { name: "Matches", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "Reference", exact: true }).click();
  await expect(page.getByText("Reference reading · hand-authored")).toBeVisible();
  await page.getByRole("button", { name: "Resume draft", exact: true }).click();
  await expect(page.getByText("Model translation · draft")).toBeVisible();
});
