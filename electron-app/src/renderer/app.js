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

// Tahapan yang ditampilkan sebagai step-tracker, urut sesuai pipeline.
const STEPS = [
  { key: "download", label: "Unduh" },
  { key: "transcribe", label: "Transkrip" },
  { key: "analyze", label: "Analisis AI" },
  { key: "render", label: "Render" },
];
const STAGE_TO_STEP = {
  downloading: "download",
  transcribing: "transcribe",
  analyzing: "analyze",
  rendering: "render",
};
// Stage yang berjalan tapi progress bisa 0 -> bar indeterminate biar tak terlihat freeze.
const PROCESSING_STAGES = new Set([
  "queued",
  "downloading",
  "transcribing",
  "analyzing",
  "rendering",
]);

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
  const stepsEl = doc.getElementById("steps");
  const elapsedEl = doc.getElementById("elapsed");
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
  let activeStepKey = null;
  let timerId = null;
  let startMs = 0;

  function setStatus(stage, message) {
    statusSection.classList.add("visible");
    statusText.textContent = message || STAGE_LABELS[stage] || stage;
    statusText.classList.toggle("error", stage === "error");
  }

  function renderSteps() {
    if (!stepsEl) return;
    stepsEl.innerHTML = "";
    for (const s of STEPS) {
      const li = doc.createElement("li");
      li.dataset.step = s.key;
      li.className = "pending";
      li.innerHTML = `<span class="dot" aria-hidden="true"></span><span>${s.label}</span>`;
      stepsEl.appendChild(li);
    }
  }

  function setStepClass(key, cls) {
    const li = stepsEl && stepsEl.querySelector(`[data-step="${key}"]`);
    if (li) li.className = cls;
  }

  function updateSteps(stage) {
    if (!stepsEl) return;
    if (stage === "error") {
      if (activeStepKey) setStepClass(activeStepKey, "error");
      return;
    }
    if (stage === "ready") {
      // Analisis selesai; render belum jalan.
      for (const s of STEPS) setStepClass(s.key, s.key === "render" ? "pending" : "done");
      activeStepKey = null;
      return;
    }
    if (stage === "done") {
      for (const s of STEPS) setStepClass(s.key, "done");
      activeStepKey = null;
      return;
    }
    const activeKey = STAGE_TO_STEP[stage];
    if (!activeKey) return;
    activeStepKey = activeKey;
    const activeIdx = STEPS.findIndex((s) => s.key === activeKey);
    STEPS.forEach((s, i) => {
      setStepClass(s.key, i < activeIdx ? "done" : i === activeIdx ? "active" : "pending");
    });
  }

  function startTimer() {
    stopTimer();
    startMs = Date.now();
    if (elapsedEl) elapsedEl.textContent = formatTime(0);
    timerId = win.setInterval(() => {
      if (elapsedEl) elapsedEl.textContent = formatTime((Date.now() - startMs) / 1000);
    }, 1000);
  }

  function stopTimer() {
    if (timerId) {
      win.clearInterval(timerId);
      timerId = null;
    }
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
      // Headline: label tahap yang stabil; kecuali error yang menampilkan pesan backend.
      const headline = data.stage === "error" ? data.message : STAGE_LABELS[data.stage];
      setStatus(data.stage, headline);
      updateSteps(data.stage);
      progressBar.value = data.progress;
      // Bar indeterminate saat tahap jalan tapi belum ada persen -> tak terlihat freeze.
      const indeterminate = data.progress === 0 && PROCESSING_STAGES.has(data.stage);
      progressBar.classList.toggle("indeterminate", indeterminate);
      // Detail live (mis. "5.0 MB / 15.0 MB" atau "Transkripsi 55%").
      progressMessage.textContent = data.message || "";
      if (data.stage === "ready" || data.stage === "done" || data.stage === "error") {
        stopTimer();
      }
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
      renderSteps();
      startTimer();
      setStatus("queued");
      progressBar.value = 0;
      progressBar.classList.add("indeterminate");
      connectWebSocket();
    } catch (err) {
      stopTimer();
      setStatus("error", `Tidak bisa terhubung ke backend: ${err.message}`);
    } finally {
      submitBtn.disabled = false;
    }
  });

  renderBtn.addEventListener("click", async () => {
    renderBtn.disabled = true;
    startTimer();
    updateSteps("rendering");
    setStatus("rendering", STAGE_LABELS.rendering);
    progressBar.value = 0;
    progressBar.classList.add("indeterminate");
    await fetch(`${API_BASE}/jobs/${jobId}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_ids: [...selected] }),
    });
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
