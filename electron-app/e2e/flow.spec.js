// Smoke test E2E alur utama dengan backend di-mock.
// Jalankan: npm run e2e
const { test, expect } = require("@playwright/test");
const { launchApp } = require("./launch-helper");

const SEGMENTS = {
  segments: [
    {
      id: "0",
      start: 10,
      end: 35,
      score: 92,
      title: "Hook Pembuka",
      reason: "hook kuat",
    },
    {
      id: "1",
      start: 60,
      end: 95,
      score: 78,
      title: "Insight Utama",
      reason: "insight",
    },
  ],
};

const OUTPUT = {
  files: [
    {
      segment_id: "0",
      path: "/Users/test/Movies/AutoClip/klip_e2e.mp4",
      duration: 25,
    },
  ],
};

test("alur utama: submit link -> segmen -> render -> selesai", async () => {
  const app = await launchApp();
  const page = app.page;

  // Mock HTTP backend.
  await page.route("http://127.0.0.1:8237/**", async (route, request) => {
    const url = request.url();
    const method = request.method();

    if (url.endsWith("/jobs") && method === "POST") {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ job_id: "job-e2e", status: "queued" }),
      });
    }
    if (url.includes("/jobs/job-e2e/segments") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(SEGMENTS),
      });
    }
    if (url.includes("/jobs/job-e2e/render") && method === "POST") {
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ render_job_id: "job-e2e", status: "queued" }),
      });
    }
    if (url.includes("/jobs/job-e2e/output") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(OUTPUT),
      });
    }
    return route.continue();
  });

  // Mock WebSocket agar progress bisa dikendalikan dari test.
  await page.evaluate(() => {
    class FakeWS {
      constructor(url) {
        this.url = url;
        this._queue = [];
        this.onmessage = null;
        FakeWS._instances.push(this);
      }
      _flush() {
        if (this.onmessage) {
          this._queue.forEach((ev) => this.onmessage(ev));
          this._queue = [];
        }
      }
      _emit(event) {
        const ev = { data: JSON.stringify(event) };
        if (this.onmessage) this.onmessage(ev);
        else this._queue.push(ev);
      }
      send() {}
      close() {}
    }
    FakeWS._instances = [];
    Object.defineProperty(FakeWS.prototype, "onmessage", {
      set(fn) {
        this._onmessage = fn;
        this._flush();
      },
      get() {
        return this._onmessage;
      },
    });
    window.__emitWS = (event) => {
      FakeWS._instances.forEach((instance) => instance._emit(event));
    };
    window.WebSocket = FakeWS;
  });

  await expect(page.getByPlaceholder(/link youtube/i)).toBeVisible();
  await page.getByPlaceholder(/link youtube/i).fill("https://www.youtube.com/watch?v=e2e123");
  await page.getByRole("button", { name: /ambil transkrip/i }).click();

  // Tunggu sampai app membuat WebSocket (instance FakeWS) sebelum emit event.
  await page.waitForFunction(() => window.WebSocket._instances?.length > 0);

  // Simulasi progress sampai segmen siap.
  await page.evaluate(() => {
    window.__emitWS({ stage: "downloading", progress: 30, message: "" });
    window.__emitWS({ stage: "ready", progress: 100, message: "" });
  });

  await expect(page.getByText("Hook Pembuka")).toBeVisible();
  await expect(page.getByText("Insight Utama")).toBeVisible();

  // Pilih segmen dan render.
  await page.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: /render terpilih/i }).click();

  await page.evaluate(() => {
    window.__emitWS({ stage: "rendering", progress: 60, message: "" });
    window.__emitWS({ stage: "done", progress: 100, message: "Render selesai" });
  });

  await expect(page.locator(".success-banner")).toBeVisible();
  await expect(page.getByText(/klip_e2e\.mp4/)).toBeVisible();
  await expect(page.getByRole("button", { name: /buka folder output/i })).toBeVisible();

  await app.close();
});
