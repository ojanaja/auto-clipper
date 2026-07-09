const API_BASE = "http://127.0.0.1:8237";
const WS_BASE = "ws://127.0.0.1:8237";

const STAGE_LABELS = {
  queued: "Masuk antrian",
  downloading: "Mengunduh video",
  transcribing: "Transkripsi audio",
  analyzing: "Mencari momen menarik",
  ready: "Segmen siap dipilih",
  rendering: "Merender klip",
  done: "Selesai",
  error: "Gagal",
};

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function setupApp(doc) {
  const win = doc.defaultView;
  const form = doc.getElementById("job-form");
  const urlInput = doc.getElementById("url-input");
  const submitBtn = doc.getElementById("submit-btn");
  const statusSection = doc.getElementById("status-section");
  const statusText = doc.getElementById("status-text");
  const progressBar = doc.getElementById("progress-bar");
  const progressMessage = doc.getElementById("progress-message");
  const segmentsSection = doc.getElementById("segments-section");
  const segmentsEl = doc.getElementById("segments");
  const renderBtn = doc.getElementById("render-btn");
  const selectAllBtn = doc.getElementById("select-all-btn");
  const clearBtn = doc.getElementById("clear-btn");
  const outputSection = doc.getElementById("output-section");
  const filesList = doc.getElementById("files-list");
  const openFolderBtn = doc.getElementById("open-folder-btn");

  let jobId = null;
  const selected = new Set();
  let segmentData = [];

  function setStatus(stage, message) {
    statusSection.classList.add("visible");
    statusText.textContent = message || STAGE_LABELS[stage] || stage;
    statusText.classList.toggle("error", stage === "error");
  }

  function updateRenderButton() {
    renderBtn.disabled = selected.size === 0;
    selectAllBtn.disabled = segmentData.length === 0 || selected.size === segmentData.length;
    clearBtn.disabled = selected.size === 0;
  }

  function updateSegmentVisualState(label, isSelected) {
    label.classList.toggle("selected", isSelected);
  }

  function renderSegments(segments) {
    segmentsEl.innerHTML = "";
    selected.clear();
    segmentData = segments;
    for (const seg of segments) {
      const label = doc.createElement("label");
      label.className = "segment";
      label.innerHTML = `
        <input type="checkbox" data-id="${seg.id}" aria-label="Pilih ${seg.title}" />
        <div>
          <div class="segment-title">${seg.title} <span class="score">${seg.score}</span></div>
          <div class="segment-meta">${formatTime(seg.start)} &ndash; ${formatTime(seg.end)}</div>
          <div class="segment-reason">${seg.reason}</div>
        </div>`;
      const checkbox = label.querySelector("input");
      checkbox.addEventListener("change", (e) => {
        if (e.target.checked) selected.add(seg.id);
        else selected.delete(seg.id);
        updateSegmentVisualState(label, e.target.checked);
        updateRenderButton();
      });
      label.addEventListener("click", (e) => {
        if (e.target !== checkbox) {
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new win.Event("change"));
        }
      });
      segmentsEl.appendChild(label);
    }
    segmentsSection.classList.add("visible");
    updateRenderButton();
  }

  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", () => {
      const checkboxes = segmentsEl.querySelectorAll('input[type="checkbox"]');
      checkboxes.forEach((cb) => {
        cb.checked = true;
        cb.dispatchEvent(new win.Event("change"));
      });
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const checkboxes = segmentsEl.querySelectorAll('input[type="checkbox"]');
      checkboxes.forEach((cb) => {
        cb.checked = false;
        cb.dispatchEvent(new win.Event("change"));
      });
    });
  }

  async function loadSegments() {
    const resp = await fetch(`${API_BASE}/jobs/${jobId}/segments`);
    const data = await resp.json();
    renderSegments(data.segments);
  }

  async function loadOutput() {
    const resp = await fetch(`${API_BASE}/jobs/${jobId}/output`);
    const data = await resp.json();
    filesList.innerHTML = "";
    if (data.files.length === 0) {
      const empty = doc.createElement("li");
      empty.className = "empty-state";
      empty.textContent = "Belum ada file output.";
      filesList.appendChild(empty);
    } else {
      for (const f of data.files) {
        const li = doc.createElement("li");
        li.innerHTML = `<span title="${f.path}">${f.path}</span><span class="file-duration">${formatTime(f.duration)}</span>`;
        filesList.appendChild(li);
      }
    }
    outputSection.classList.add("visible");
  }

  function connectWebSocket() {
    const ws = new WebSocket(`${WS_BASE}/ws/jobs/${jobId}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.stage === "connected") return;
      setStatus(data.stage, data.message);
      progressBar.value = data.progress;
      progressMessage.textContent = STAGE_LABELS[data.stage] || "";
      if (data.stage === "ready") loadSegments();
      if (data.stage === "done") loadOutput();
    };
    ws.onerror = () => {
      setStatus("error", "Koneksi progress terputus. Coba kirim ulang link.");
    };
    ws.onclose = () => {
      // Jika belum sampai ready/done, tampilkan petunjuk.
      if (statusText.textContent === STAGE_LABELS.queued) {
        setStatus("error", "Proses belum dimulai. Periksa log backend atau coba video lain.");
      }
    };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submitBtn.disabled = true;
    try {
      const resp = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: urlInput.value }),
      });
      const data = await resp.json();
      jobId = data.job_id;
      setStatus("queued");
      progressBar.value = 0;
      connectWebSocket();
    } catch (err) {
      setStatus("error", `Tidak bisa terhubung ke backend: ${err.message}`);
    } finally {
      submitBtn.disabled = false;
    }
  });

  renderBtn.addEventListener("click", async () => {
    renderBtn.disabled = true;
    await fetch(`${API_BASE}/jobs/${jobId}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_ids: [...selected] }),
    });
    setStatus("rendering", "Render dimulai");
  });

  openFolderBtn.addEventListener("click", () => {
    if (typeof window !== "undefined" && window.autoclip) {
      window.autoclip.openOutputFolder();
    }
  });
}

if (typeof module !== "undefined") {
  module.exports = { setupApp, formatTime };
}

if (typeof window !== "undefined" && window.document && !window.__AUTOCLIP_TEST__) {
  // Electron renderer: jalankan langsung.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupApp(document));
  } else if (document.getElementById("job-form")) {
    setupApp(document);
  }
}
