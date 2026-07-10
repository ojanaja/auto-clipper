// E2E smoke panel Settings: buka, load config (mocked), ubah, simpan.
const { test, expect } = require("@playwright/test");
const { launchApp } = require("./launch-helper");

const MOCK_CONFIG = {
  aspect_ratio: "9:16",
  resolution: 1080,
  duration_min: 20,
  duration_max: 60,
  subtitle_enabled: true,
  subtitle_font_size: 80,
  whisper_model: "small",
  segment_count: 8,
  llm_provider: "gemini",
  llm_model: "",
  gemini_key_set: true,
  anthropic_key_set: false,
  encoder: "auto",
  output_dir: "",
  face_tracking_enabled: false,
  face_sample_fps: 2,
  speaker_min_dwell_s: 1.5,
};

test("panel settings load, edit, dan save config", async () => {
  const app = await launchApp();
  const page = app.page;

  await page.route("**/config", async (route) => {
    const req = route.request();
    if (req.method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_CONFIG),
      });
    }
    if (req.method() === "PUT") {
      const body = await req.postDataJSON();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...MOCK_CONFIG, ...body }),
      });
    }
    return route.continue();
  });

  await page.locator("#settings-btn").click();
  await expect(page.locator("#settings-section")).toBeVisible();

  // Config awal ter-load.
  await expect(page.locator("#cfg-aspect-ratio")).toHaveValue("9:16");
  await expect(page.locator("#cfg-resolution")).toHaveValue("1080");
  await expect(page.locator("#cfg-subtitle-enabled")).toBeChecked();

  // Ubah rasio & resolusi, lalu simpan.
  await page.locator("#cfg-aspect-ratio").selectOption("1:1");
  await page.locator("#cfg-resolution").selectOption("720");
  await page.locator("#settings-form button[type='submit']").click();

  await expect(page.locator("#settings-status")).toHaveText(/tersimpan/i);

  await app.close();
});
