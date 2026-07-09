// Smoke test E2E: launch Electron, verifikasi UI dasar tampil.
// Jalankan manual/sebelum rilis: npm run e2e
const { test, expect } = require("@playwright/test");
const { launchApp } = require("./launch-helper");

test("app terbuka dan form input tampil", async () => {
  const app = await launchApp();
  const page = app.page;

  await expect(page).toHaveTitle(/AutoClip Lokal/);
  await expect(page.getByPlaceholder(/link youtube/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /ambil transkrip/i })).toBeVisible();
  // Section segmen & output tersembunyi sebelum ada job.
  await expect(page.locator("#segments-section")).toBeHidden();
  await expect(page.locator("#output-section")).toBeHidden();

  await app.close();
});
