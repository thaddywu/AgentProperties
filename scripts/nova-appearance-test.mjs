import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";

const { chromium } = process.env.NOVA_PLAYWRIGHT_MODULE
  ? await import(process.env.NOVA_PLAYWRIGHT_MODULE)
  : createRequire(new URL("../apps/web/package.json", import.meta.url))("@playwright/test");
const base = process.env.NOVA_URL ?? "http://127.0.0.1:5180";
const output = process.env.NOVA_SCREENSHOTS ?? "/tmp/nova-appearance-review";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.NOVA_CHROMIUM ? { executablePath: process.env.NOVA_CHROMIUM } : {}),
  args: ["--no-sandbox"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1500, height: 1000 },
    colorScheme: "dark",
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const expectTheme = async (theme) => {
    await page.waitForFunction(
      (value) => document.documentElement.dataset.theme === value,
      theme,
    );
    assert.equal(await page.locator("html").evaluate((el) => el.style.colorScheme), theme);
    await page.getByRole("button", {
      name: theme === "light" ? "Switch to dark mode" : "Switch to light mode",
      exact: true,
    }).waitFor();
  };
  await page.goto(`${base}/nova.html`);
  await page.getByRole("tab", { name: "Query", exact: true }).waitFor();
  await expectTheme("dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expectTheme("light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expectTheme("dark");
  const background = () => page.locator("main").evaluate((el) => getComputedStyle(el).backgroundColor);
  const darkBackground = await background();
  await page.getByRole("button", { name: "Switch to light mode", exact: true }).click();
  await expectTheme("light");
  assert.notEqual(await background(), darkBackground);
  await page.reload();
  await page.getByRole("tab", { name: "Query", exact: true }).waitFor();
  await expectTheme("light");
  await page.emulateMedia({ colorScheme: "light" });
  await page.emulateMedia({ colorScheme: "dark" });
  await expectTheme("light");
  await page.screenshot({ path: `${output}/light.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Switch to dark mode", exact: true }).click();
  await expectTheme("dark");
  await page.reload();
  await expectTheme("dark");
  await page.getByRole("button", { name: "Switch to light mode", exact: true }).click();
  await expectTheme("light");
  await page.screenshot({ path: `${output}/light-mobile.png`, fullPage: true });
  assert.deepEqual(errors, []);
  console.log("PASS system appearance, light/dark toggle, reload persistence, and narrow viewport");
} finally {
  await browser.close();
}
