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
