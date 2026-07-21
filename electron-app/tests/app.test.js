const { screen, within } = require("@testing-library/dom");
const userEvent = require("@testing-library/user-event").default;
const { loadApp, mockFetchQueue, FakeWebSocket } = require("./helpers");

const SEGMENTS = {
  segments: [
    { id: "0", start: 10, end: 35, score: 92, title: "Hook Pembuka", reason: "hook kuat" },
    { id: "1", start: 60, end: 95, score: 78, title: "Insight Utama", reason: "insight" },
  ],
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
});
