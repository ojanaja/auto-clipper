const { screen, within } = require("@testing-library/dom");
const userEvent = require("@testing-library/user-event").default;
const { loadApp, mockFetchQueue, FakeWebSocket } = require("./helpers");

const SEGMENTS = {
  segments: [
    { id: "0", start: 10, end: 35, score: 92, title: "Hook Pembuka", reason: "hook kuat" },
    { id: "1", start: 60, end: 95, score: 78, title: "Insight Utama", reason: "insight" },
  ],
};

const CUSTOM_DEFAULT = {
  enabled: false,
  subtitle: { enabled: true },
  overlay_sumber: { enabled: false },
  watermark: { enabled: false },
  overlay_gambar: { enabled: false },
  color_grade: { enabled: false },
};

function flush() {
  return new Promise((r) => setTimeout(r, 0));
}

describe("input link & status job", () => {
  test("submit link memanggil POST /jobs dan menampilkan status", async () => {
    const fetchMock = mockFetchQueue([{ job_id: "job-1", status: "queued" }]);
    loadApp();

    await userEvent.type(
      screen.getByPlaceholderText(/link youtube/i),
      "https://www.youtube.com/watch?v=abc12345678"
    );
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain("/jobs");
    expect(JSON.parse(opts.body)).toEqual({
      youtube_url: "https://www.youtube.com/watch?v=abc12345678",
    });
    expect(screen.getByText(/antrian/i)).toBeInTheDocument();
  });

  test("submit retry saat backend belum siap (cold start), lalu berhasil", async () => {
    let calls = 0;
    global.fetch = jest.fn(() => {
      calls += 1;
      if (calls === 1) return Promise.reject(new TypeError("Failed to fetch"));
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ job_id: "job-1", status: "queued" }),
      });
    });
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();
    expect(screen.getByText(/menyiapkan backend/i)).toBeInTheDocument();

    await new Promise((r) => setTimeout(r, 1600));
    await flush();

    expect(calls).toBe(2);
    expect(screen.getByText(/antrian/i)).toBeInTheDocument();
  }, 10000);

  test("membuka WebSocket ke job yang dibuat", async () => {
    mockFetchQueue([{ job_id: "job-42", status: "queued" }]);
    loadApp();

    await userEvent.type(
      screen.getByPlaceholderText(/link youtube/i),
      "https://youtu.be/abc12345678"
    );
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain("/ws/jobs/job-42");
  });

  test("tombol Coba Lagi muncul saat error tahap analisis, retry lewat endpoint checkpoint", async () => {
    mockFetchQueue([
      { job_id: "job-1", status: "queued" },
      { job_id: "job-1", status: "retrying" },
    ]);
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();

    const retryBtn = document.getElementById("retry-btn");
    expect(retryBtn).toHaveAttribute("hidden");

    FakeWebSocket.instances[0].emit({
      stage: "error",
      progress: 0,
      message: "Koneksi terputus saat mengunduh video",
      resumable: true,
    });
    await flush();
    expect(retryBtn).not.toHaveAttribute("hidden");

    await userEvent.click(retryBtn);
    await flush();

    const fetchMock = global.fetch;
    const retryCall = fetchMock.mock.calls.find(([u]) => u.includes("/retry"));
    expect(retryCall[0]).toContain("/jobs/job-1/retry");
    expect(retryCall[1].method).toBe("POST");
    expect(retryBtn).toHaveAttribute("hidden");
    expect(screen.getByText(/antrian/i)).toBeInTheDocument();
  });

  test("tombol Coba Lagi disembunyikan untuk error yang tidak resumable (mis. API key ditolak)", async () => {
    mockFetchQueue([{ job_id: "job-1", status: "queued" }]);
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();

    FakeWebSocket.instances[0].emit({
      stage: "error",
      progress: 0,
      message: "GEMINI_API_KEY belum diset",
      resumable: false,
    });
    await flush();

    expect(document.getElementById("retry-btn")).toHaveAttribute("hidden");
  });

  test("event WS mengubah status dan progress bar", async () => {
    mockFetchQueue([{ job_id: "job-1", status: "queued" }]);
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();

    FakeWebSocket.instances[0].emit({
      stage: "downloading",
      progress: 40,
      message: "Mengunduh video",
    });

    expect(document.getElementById("status-text")).toHaveTextContent(/mengunduh video/i);
    expect(document.getElementById("progress-bar").value).toBe(40);
  });

  test("event error menampilkan pesan error", async () => {
    mockFetchQueue([{ job_id: "job-1", status: "queued" }]);
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();

    FakeWebSocket.instances[0].emit({ stage: "error", progress: 0, message: "Video privat" });

    const status = document.getElementById("status-text");
    expect(status).toHaveTextContent(/video privat/i);
    expect(status.classList.contains("error")).toBe(true);
  });
});

describe("visibilitas progress (anti-freeze)", () => {
  const step = (key) => document.querySelector(`[data-step="${key}"]`);

  async function submit() {
    mockFetchQueue([{ job_id: "job-1", status: "queued" }, { segments: [] }]);
    loadApp();
    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();
    return FakeWebSocket.instances[0];
  }

  test("step tracker menandai tahap aktif, selesai, dan menunggu", async () => {
    const ws = await submit();

    ws.emit({ stage: "downloading", progress: 10, message: "" });
    expect(step("download")).toHaveClass("active");
    expect(step("transcribe")).toHaveClass("pending");

    ws.emit({ stage: "transcribing", progress: 0, message: "" });
    expect(step("download")).toHaveClass("done");
    expect(step("transcribe")).toHaveClass("active");

    ws.emit({ stage: "ready", progress: 100, message: "" });
    expect(step("download")).toHaveClass("done");
    expect(step("transcribe")).toHaveClass("done");
    expect(step("analyze")).toHaveClass("done");
    expect(step("render")).toHaveClass("pending");
  });

  test("tahap aktif menampilkan tanda error saat gagal", async () => {
    const ws = await submit();
    ws.emit({ stage: "downloading", progress: 20, message: "" });
    ws.emit({ stage: "error", progress: 0, message: "Video privat" });

    expect(step("download")).toHaveClass("error");
  });

  test("progress bar indeterminate saat progress 0, determinate saat ada persen", async () => {
    const ws = await submit();
    const bar = document.getElementById("progress-bar");

    ws.emit({ stage: "transcribing", progress: 0, message: "" });
    expect(bar.classList.contains("indeterminate")).toBe(true);

    ws.emit({ stage: "transcribing", progress: 55, message: "Transkripsi 55%" });
    expect(bar.classList.contains("indeterminate")).toBe(false);
    expect(bar.value).toBe(55);
  });

  test("timer elapsed mulai berjalan saat submit", async () => {
    await submit();
    expect(document.getElementById("elapsed")).toHaveTextContent(/0:00/);
  });

  test("pesan detail progress tampil dari message backend", async () => {
    const ws = await submit();
    ws.emit({ stage: "downloading", progress: 33, message: "5.0 MB / 15.0 MB" });
    expect(document.getElementById("progress-message")).toHaveTextContent(/5\.0 MB/);
  });
});

describe("jeda preview: unduh & transkrip", () => {
  async function submit() {
    mockFetchQueue([{ job_id: "job-1", status: "queued" }]);
    loadApp();
    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();
    return FakeWebSocket.instances[0];
  }

  test("stage download_ready menampilkan preview video & step download selesai", async () => {
    const ws = await submit();
    mockFetchQueue([
      {
        video_title: "Judul Video",
        video_duration: 125,
        video_width: 1920,
        video_height: 1080,
        has_thumbnail: true,
      },
    ]);

    ws.emit({ stage: "download_ready", progress: 100, message: "Video siap" });
    await flush();

    expect(document.getElementById("download-preview-section")).toHaveClass("visible");
    expect(document.getElementById("download-preview-title")).toHaveTextContent("Judul Video");
    expect(document.getElementById("download-preview-meta")).toHaveTextContent(/2:05/);
    expect(document.getElementById("download-preview-thumb").src).toContain(
      "/jobs/job-1/thumbnail"
    );
    expect(document.querySelector('[data-step="download"]')).toHaveClass("done");
    expect(document.querySelector('[data-step="transcribe"]')).toHaveClass("pending");
  });

  test("thumbnail disembunyikan kalau video tidak punya thumbnail", async () => {
    const ws = await submit();
    mockFetchQueue([{ video_title: "V", video_duration: 10, has_thumbnail: false }]);

    ws.emit({ stage: "download_ready", progress: 100, message: "" });
    await flush();

    expect(document.getElementById("download-preview-thumb")).toHaveAttribute("hidden");
  });

  test("klik Lanjutkan di preview unduhan memanggil POST /continue", async () => {
    const ws = await submit();
    mockFetchQueue([{ video_title: "V", video_duration: 10 }]);
    ws.emit({ stage: "download_ready", progress: 100, message: "" });
    await flush();

    const fetchMock = mockFetchQueue([{ job_id: "job-1", status: "continuing" }]);
    await userEvent.click(screen.getByRole("button", { name: /lanjutkan ke transkrip/i }));
    await flush();

    const call = fetchMock.mock.calls.find(([u]) => u.includes("/continue"));
    expect(call[0]).toContain("/jobs/job-1/continue");
    expect(call[1].method).toBe("POST");
  });

  test("preview unduhan sembunyi lagi begitu stage lanjut ke transcribing", async () => {
    const ws = await submit();
    mockFetchQueue([{ video_title: "V", video_duration: 10 }]);
    ws.emit({ stage: "download_ready", progress: 100, message: "" });
    await flush();
    expect(document.getElementById("download-preview-section")).toHaveClass("visible");

    ws.emit({ stage: "transcribing", progress: 0, message: "" });
    await flush();
    expect(document.getElementById("download-preview-section")).not.toHaveClass("visible");
  });

  test("stage transcript_ready menampilkan preview teks transkrip", async () => {
    const ws = await submit();
    mockFetchQueue([{ text: "halo dunia ini transkrip" }]);

    ws.emit({ stage: "transcript_ready", progress: 100, message: "" });
    await flush();

    expect(document.getElementById("transcript-preview-section")).toHaveClass("visible");
    expect(document.getElementById("transcript-preview-text")).toHaveTextContent(
      "halo dunia ini transkrip"
    );
    expect(document.querySelector('[data-step="transcribe"]')).toHaveClass("done");
    expect(document.querySelector('[data-step="analyze"]')).toHaveClass("pending");
  });

  test("klik Lanjutkan di preview transkrip memanggil POST /continue", async () => {
    const ws = await submit();
    mockFetchQueue([{ text: "halo" }]);
    ws.emit({ stage: "transcript_ready", progress: 100, message: "" });
    await flush();

    const fetchMock = mockFetchQueue([{ job_id: "job-1", status: "continuing" }]);
    await userEvent.click(screen.getByRole("button", { name: /lanjutkan ke analisis ai/i }));
    await flush();

    const call = fetchMock.mock.calls.find(([u]) => u.includes("/continue"));
    expect(call[0]).toContain("/jobs/job-1/continue");
  });
});

describe("daftar segmen & seleksi", () => {
  async function readyApp() {
    mockFetchQueue([{ job_id: "job-1", status: "queued" }, SEGMENTS]);
    loadApp();
    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();
    FakeWebSocket.instances[0].emit({ stage: "ready", progress: 100, message: "2 segmen" });
    await flush();
  }

  test("stage ready menampilkan segmen dengan judul dan skor", async () => {
    await readyApp();

    expect(screen.getByText("Hook Pembuka")).toBeInTheDocument();
    expect(screen.getByText("Insight Utama")).toBeInTheDocument();
    expect(screen.getByText("92")).toBeInTheDocument();
    // Timestamp mm:ss tampil.
    expect(screen.getByText(/0:10/)).toBeInTheDocument();
  });

  test("tombol render disabled tanpa pilihan, aktif setelah centang", async () => {
    await readyApp();
    const renderBtn = screen.getByRole("button", { name: /render terpilih/i });
    expect(renderBtn).toBeDisabled();

    const checkboxes = screen.getAllByRole("checkbox");
    await userEvent.click(checkboxes[0]);
    expect(renderBtn).toBeEnabled();

    await userEvent.click(checkboxes[0]);
    expect(renderBtn).toBeDisabled();
  });

  test("klik render kirim segment_ids terpilih", async () => {
    await readyApp();
    const fetchMock = global.fetch;

    await userEvent.click(screen.getAllByRole("checkbox")[1]);
    await userEvent.click(screen.getByRole("button", { name: /render terpilih/i }));
    await flush();

    const renderCall = fetchMock.mock.calls.find(([u]) => u.includes("/render"));
    expect(renderCall).toBeDefined();
    expect(JSON.parse(renderCall[1].body)).toEqual({ segment_ids: ["1"] });
  });

  test("tombol pilih semua / batal pilih mengontrol semua checkbox", async () => {
    await readyApp();
    const checkboxes = screen.getAllByRole("checkbox");
    const renderBtn = screen.getByRole("button", { name: /render terpilih/i });

    await userEvent.click(screen.getByRole("button", { name: /pilih semua/i }));
    expect(renderBtn).toBeEnabled();
    checkboxes.forEach((cb) => expect(cb).toBeChecked());

    await userEvent.click(screen.getByRole("button", { name: /batal pilih/i }));
    expect(renderBtn).toBeDisabled();
    checkboxes.forEach((cb) => expect(cb).not.toBeChecked());
  });

  test("kartu segmen mendapatkan kelas selected saat dicentang", async () => {
    await readyApp();
    const segment = document.querySelectorAll(".segment")[0];
    expect(segment.classList.contains("selected")).toBe(false);

    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(segment.classList.contains("selected")).toBe(true);
  });
});

describe("pengaturan", () => {
  const DEFAULT_CONFIG = {
    aspect_ratio: "1:1",
    resolution: 720,
    duration_min: 30,
    duration_max: 90,
    subtitle_enabled: true,
    subtitle_font_size: 64,
    whisper_model: "tiny",
    segment_count: 5,
    llm_provider: "anthropic",
    llm_model: "claude-test",
    gemini_key_set: true,
    anthropic_key_set: false,
    encoder: "libx264",
    output_dir: "/tmp/out",
    face_tracking_enabled: true,
    face_sample_fps: 3,
    speaker_min_dwell_s: 1.2,
  };

  async function openSettings() {
    await userEvent.click(screen.getByRole("button", { name: /pengaturan/i }));
    await flush();
  }

  test("membuka panel pengaturan dan memuat konfigurasi", async () => {
    mockFetchQueue([DEFAULT_CONFIG]);
    loadApp();
    await openSettings();

    const section = document.getElementById("settings-section");
    expect(section).not.toHaveAttribute("hidden");
    expect(section).toHaveClass("visible");

    const fetchMock = global.fetch;
    const configCall = fetchMock.mock.calls.find(([u]) => u.includes("/config"));
    expect(configCall).toBeDefined();

    expect(document.getElementById("cfg-aspect-ratio").value).toBe("1:1");
    expect(document.getElementById("cfg-resolution").value).toBe("720");
    expect(document.getElementById("cfg-subtitle-enabled").checked).toBe(true);
    expect(document.getElementById("cfg-face-tracking-enabled").checked).toBe(true);
    expect(document.getElementById("cfg-face-sample-fps").value).toBe("3");
    expect(document.getElementById("cfg-speaker-min-dwell").value).toBe("1.2");
    expect(document.getElementById("cfg-output-dir").value).toBe("/tmp/out");
    expect(document.getElementById("gemini-key-set")).not.toHaveAttribute("hidden");
    expect(document.getElementById("anthropic-key-set")).toHaveAttribute("hidden");
  });

  test("menyimpan perubahan via PUT /config", async () => {
    mockFetchQueue([DEFAULT_CONFIG, DEFAULT_CONFIG]);
    loadApp();
    await openSettings();

    await userEvent.clear(screen.getByLabelText(/durasi min/i));
    await userEvent.type(screen.getByLabelText(/durasi min/i), "25");
    await userEvent.click(screen.getByRole("button", { name: /simpan/i }));
    await flush();

    const fetchMock = global.fetch;
    const putCall = fetchMock.mock.calls.find(
      ([u, opts]) => u.includes("/config") && opts && opts.method === "PUT"
    );
    expect(putCall).toBeDefined();
    const body = JSON.parse(putCall[1].body);
    expect(body.duration_min).toBe(25);
    expect(body.aspect_ratio).toBe("1:1");
    expect(body.subtitle_enabled).toBe(true);
    expect(body.face_tracking_enabled).toBe(true);
    expect(body.face_sample_fps).toBe(3);
    expect(body.speaker_min_dwell_s).toBe(1.2);
    // API key kosong tidak dikirim supaya tidak menghapus key tersimpan.
    expect(body).not.toHaveProperty("gemini_api_key");
    expect(body).not.toHaveProperty("anthropic_api_key");
  });

  test("tombol tutup menutup panel pengaturan", async () => {
    mockFetchQueue([DEFAULT_CONFIG]);
    loadApp();
    await openSettings();
    await userEvent.click(screen.getByRole("button", { name: /tutup/i }));

    const section = document.getElementById("settings-section");
    expect(section).toHaveAttribute("hidden");
    expect(section).not.toHaveClass("visible");
  });
});

describe("progress render & output", () => {
  test("stage done menampilkan daftar file output", async () => {
    mockFetchQueue([
      { job_id: "job-1", status: "queued" },
      SEGMENTS,
      { render_job_id: "job-1", status: "queued" },
      { files: [{ segment_id: "0", path: "/out/klip_a.mp4", duration: 25 }] },
    ]);
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();
    const ws = FakeWebSocket.instances[0];
    ws.emit({ stage: "ready", progress: 100, message: "" });
    await flush();

    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    await userEvent.click(screen.getByRole("button", { name: /render terpilih/i }));
    await flush();
    ws.emit({ stage: "done", progress: 100, message: "Render selesai" });
    await flush();

    const list = within(document.getElementById("files-list"));
    expect(list.getByText(/klip_a\.mp4/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /buka folder output/i })).toBeVisible();
  });

  test("tombol Render aktif lagi setelah render gagal, tanpa perlu ubah centang", async () => {
    mockFetchQueue([
      { job_id: "job-1", status: "queued" },
      SEGMENTS,
      { render_job_id: "job-1", status: "queued" },
    ]);
    loadApp();

    await userEvent.type(screen.getByPlaceholderText(/link youtube/i), "https://youtu.be/x");
    await userEvent.click(screen.getByRole("button", { name: /ambil transkrip/i }));
    await flush();
    const ws = FakeWebSocket.instances[0];
    ws.emit({ stage: "ready", progress: 100, message: "" });
    await flush();

    await userEvent.click(screen.getAllByRole("checkbox")[0]);
    const renderBtn = screen.getByRole("button", { name: /render terpilih/i });
    await userEvent.click(renderBtn);
    expect(renderBtn).toBeDisabled();
    await flush();

    ws.emit({ stage: "error", progress: 0, message: "Semua klip gagal dirender." });
    await flush();

    // Klip yang sudah sukses dilewati backend saat klik lagi -> tombol harus bisa diklik.
    expect(renderBtn).toBeEnabled();
  });
});

describe("needsApiKeySetup", () => {
  test("true hanya saat provider aktif belum punya key; respons non-config diabaikan", () => {
    const { needsApiKeySetup } = require("../src/renderer/app.js");
    expect(needsApiKeySetup({ llm_provider: "gemini", gemini_key_set: false })).toBe(true);
    expect(needsApiKeySetup({ llm_provider: "gemini", gemini_key_set: true })).toBe(false);
    expect(needsApiKeySetup({ llm_provider: "anthropic", anthropic_key_set: false })).toBe(true);
    expect(needsApiKeySetup({ llm_provider: "anthropic", anthropic_key_set: true })).toBe(false);
    expect(needsApiKeySetup({ job_id: "job-1", status: "queued" })).toBe(false);
  });
});

describe("onboarding: wajib isi API key", () => {
  const NO_KEY_CONFIG = {
    llm_provider: "gemini",
    gemini_key_set: false,
    anthropic_key_set: false,
    aspect_ratio: "9:16",
    resolution: 1080,
  };

  test("form job disembunyikan & pengaturan terkunci-terbuka sampai API key diisi", async () => {
    mockFetchQueue([NO_KEY_CONFIG, { ...NO_KEY_CONFIG, gemini_key_set: true }]);
    loadApp({ autoCheck: true });
    await flush();

    const jobForm = document.getElementById("job-form");
    const section = document.getElementById("settings-section");
    expect(jobForm).toHaveAttribute("hidden");
    expect(section).not.toHaveAttribute("hidden");
    expect(section).toHaveClass("visible");
    expect(document.getElementById("settings-close")).toHaveAttribute("hidden");

    // Backdrop tidak bisa menutup panel selama API key belum ada.
    document.getElementById("settings-backdrop").click();
    expect(section).toHaveClass("visible");

    await userEvent.type(document.getElementById("cfg-gemini-key"), "AIza-test-key");
    await userEvent.click(screen.getByRole("button", { name: /simpan/i }));
    await flush();

    expect(jobForm).not.toHaveAttribute("hidden");
    expect(section).not.toHaveClass("visible");
  });
});

describe("tab navigasi utama", () => {
  test("Klip adalah tab aktif default, tab lain tersembunyi", () => {
    loadApp();
    expect(document.getElementById("tab-klip")).not.toHaveAttribute("hidden");
    expect(document.getElementById("tab-kustomisasi")).toHaveAttribute("hidden");
    expect(document.getElementById("tab-thumbnail")).toHaveAttribute("hidden");
    expect(document.getElementById("tab-autopost")).toHaveAttribute("hidden");
  });

  test("klik tab Kustomisasi menampilkan panelnya & menyembunyikan Klip", async () => {
    mockFetchQueue([CUSTOM_DEFAULT]);
    loadApp();

    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    expect(document.getElementById("tab-kustomisasi")).not.toHaveAttribute("hidden");
    expect(document.getElementById("tab-klip")).toHaveAttribute("hidden");
    expect(screen.getByRole("tab", { name: /kustomisasi/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  test("tab Thumbnail & Autopost tampil sebagai placeholder Fase 2/4", async () => {
    loadApp();

    await userEvent.click(screen.getByRole("tab", { name: /thumbnail/i }));
    expect(document.getElementById("tab-thumbnail")).not.toHaveAttribute("hidden");
    expect(screen.getByText(/fase 2/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /autopost/i }));
    expect(document.getElementById("tab-autopost")).not.toHaveAttribute("hidden");
    expect(screen.getByText(/fase 4/i)).toBeInTheDocument();
  });
});

describe("tab Kustomisasi: preset kerangka (Fase 1a)", () => {
  test("membuka tab memuat config dari GET /customization", async () => {
    mockFetchQueue([{ ...CUSTOM_DEFAULT, enabled: true, watermark: { enabled: true } }]);
    loadApp();

    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    expect(document.getElementById("kustom-enabled")).toBeChecked();
    expect(document.getElementById("kustom-watermark-enabled")).toBeChecked();
    expect(document.getElementById("kustom-dot-watermark")).toHaveClass("on");
    expect(document.getElementById("kustom-subtitle-enabled")).toBeChecked();
  });

  test("toggle Aktifkan Kustomisasi mengirim PUT /customization", async () => {
    const fetchMock = mockFetchQueue([CUSTOM_DEFAULT, { ...CUSTOM_DEFAULT, enabled: true }]);
    loadApp();
    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    await userEvent.click(document.getElementById("kustom-enabled"));
    await flush();

    const [url, opts] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(url).toContain("/customization");
    expect(opts.method).toBe("PUT");
    expect(JSON.parse(opts.body)).toEqual({ enabled: true });
    expect(document.getElementById("kustom-enabled")).toBeChecked();
  });

  test("toggle section Overlay Gambar mengirim payload section & menyalakan dot", async () => {
    const fetchMock = mockFetchQueue([
      CUSTOM_DEFAULT,
      { ...CUSTOM_DEFAULT, overlay_gambar: { enabled: true } },
    ]);
    loadApp();
    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    await userEvent.click(document.getElementById("kustom-overlay_gambar-enabled"));
    await flush();

    const [, opts] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(JSON.parse(opts.body)).toEqual({ overlay_gambar: { enabled: true } });
    expect(document.getElementById("kustom-dot-overlay_gambar")).toHaveClass("on");
  });

  test("Impor preset memanggil dialog file lalu menerapkan isinya", async () => {
    window.autoclip = {
      importCustomizationPreset: jest
        .fn()
        .mockResolvedValue({ enabled: true, color_grade: { enabled: true } }),
    };
    mockFetchQueue([
      CUSTOM_DEFAULT,
      { ...CUSTOM_DEFAULT, enabled: true, color_grade: { enabled: true } },
    ]);
    loadApp();
    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    await userEvent.click(screen.getByRole("button", { name: /^impor$/i }));
    await flush();

    expect(window.autoclip.importCustomizationPreset).toHaveBeenCalled();
    expect(document.getElementById("kustom-enabled")).toBeChecked();
    expect(document.getElementById("kustom-dot-color_grade")).toHaveClass("on");
    delete window.autoclip;
  });

  test("Impor dibatalkan (dialog return null) tidak mengubah apa pun", async () => {
    window.autoclip = { importCustomizationPreset: jest.fn().mockResolvedValue(null) };
    const fetchMock = mockFetchQueue([CUSTOM_DEFAULT]);
    loadApp();
    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    const callsBefore = fetchMock.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /^impor$/i }));
    await flush();

    expect(fetchMock.mock.calls.length).toBe(callsBefore);
    delete window.autoclip;
  });

  test("Ekspor preset mengambil config aktif lalu memanggil dialog simpan", async () => {
    window.autoclip = { exportCustomizationPreset: jest.fn().mockResolvedValue(true) };
    mockFetchQueue([CUSTOM_DEFAULT, CUSTOM_DEFAULT]);
    loadApp();
    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();

    await userEvent.click(screen.getByRole("button", { name: /^ekspor$/i }));
    await flush();

    expect(window.autoclip.exportCustomizationPreset).toHaveBeenCalledWith(CUSTOM_DEFAULT);
    expect(screen.getByText(/preset diekspor/i)).toBeInTheDocument();
    delete window.autoclip;
  });

  test("Reset mengembalikan preset ke default via POST /customization/reset", async () => {
    mockFetchQueue([
      { ...CUSTOM_DEFAULT, enabled: true, watermark: { enabled: true } },
      CUSTOM_DEFAULT,
    ]);
    loadApp();
    await userEvent.click(screen.getByRole("tab", { name: /kustomisasi/i }));
    await flush();
    expect(document.getElementById("kustom-enabled")).toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: /^reset$/i }));
    await flush();

    expect(document.getElementById("kustom-enabled")).not.toBeChecked();
    expect(document.getElementById("kustom-watermark-enabled")).not.toBeChecked();
  });
});
