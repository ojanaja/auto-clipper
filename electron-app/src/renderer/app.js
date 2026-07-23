const API_BASE = "http://127.0.0.1:8237";
const WS_BASE = "ws://127.0.0.1:8237";

const STAGE_LABELS = {
  queued: "Masuk antrian",
  downloading: "Mengunduh video",
  download_ready: "Video siap",
  transcribing: "Transkripsi audio",
  transcript_ready: "Transkrip siap",
  analyzing: "Mencari momen menarik",
  ready: "Segmen siap dipilih",
  rendering: "Merender klip",
  done: "Selesai",
  error: "Gagal",
};

// Jeda preview: step yang sudah pasti "done" begitu stage ini tercapai.
const STAGE_STEP_DONE_UP_TO = {
  download_ready: "download",
  transcript_ready: "transcribe",
  ready: "analyze",
  done: "render",
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
  const retryBtn = doc.getElementById("retry-btn");
  const downloadPreviewSection = doc.getElementById("download-preview-section");
  const downloadPreviewThumb = doc.getElementById("download-preview-thumb");
  const downloadPreviewTitle = doc.getElementById("download-preview-title");
  const downloadPreviewMeta = doc.getElementById("download-preview-meta");
  const downloadContinueBtn = doc.getElementById("download-continue-btn");
  const transcriptPreviewSection = doc.getElementById("transcript-preview-section");
  const transcriptPreviewText = doc.getElementById("transcript-preview-text");
  const transcriptContinueBtn = doc.getElementById("transcript-continue-btn");
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
    const doneUpTo = STAGE_STEP_DONE_UP_TO[stage];
    if (doneUpTo) {
      // Jeda preview atau tahap selesai: step sampai doneUpTo "done", sisanya nunggu.
      const doneIdx = STEPS.findIndex((s) => s.key === doneUpTo);
      STEPS.forEach((s, i) => setStepClass(s.key, i <= doneIdx ? "done" : "pending"));
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

  async function loadDownloadPreview() {
    const resp = await fetch(`${API_BASE}/jobs/${jobId}`);
    const data = await resp.json();
    downloadPreviewThumb.hidden = !data.has_thumbnail;
    downloadPreviewThumb.src = data.has_thumbnail ? `${API_BASE}/jobs/${jobId}/thumbnail` : "";
    downloadPreviewTitle.textContent = data.video_title || "(tanpa judul)";
    const dims =
      data.video_width && data.video_height ? `${data.video_width}x${data.video_height} • ` : "";
    downloadPreviewMeta.textContent = `${dims}${formatTime(data.video_duration || 0)}`;
  }

  async function loadTranscriptPreview() {
    const resp = await fetch(`${API_BASE}/jobs/${jobId}/transcript`);
    const data = await resp.json();
    transcriptPreviewText.textContent = data.text || "(tidak ada suara terdeteksi)";
  }

  async function continueJob(btn) {
    btn.disabled = true;
    try {
      await fetch(`${API_BASE}/jobs/${jobId}/continue`, { method: "POST" });
      startTimer();
      progressBar.value = 0;
      progressBar.classList.add("indeterminate");
    } finally {
      btn.disabled = false;
    }
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
      if (
        data.stage === "download_ready" ||
        data.stage === "transcript_ready" ||
        data.stage === "ready" ||
        data.stage === "done" ||
        data.stage === "error"
      ) {
        stopTimer();
      }
      // Jeda preview: section cuma tampil persis di stage-nya sendiri, robust
      // terhadap reconnect WS (data dimuat ulang dari backend, bukan disimpan di sini).
      downloadPreviewSection.classList.toggle("visible", data.stage === "download_ready");
      transcriptPreviewSection.classList.toggle("visible", data.stage === "transcript_ready");
      if (data.stage === "download_ready") loadDownloadPreview();
      if (data.stage === "transcript_ready") loadTranscriptPreview();
      if (data.stage === "ready") loadSegments();
      if (data.stage === "done") loadOutput();
      // Sembunyikan tombol submit begitu fase download jalan biar user gak
      // bisa klik ulang & nabrak job yang lagi proses; balikin kalau error
      // (termasuk non-resumable) biar bisa submit URL baru.
      if (data.stage === "downloading") submitBtn.hidden = true;
      if (data.stage === "error") submitBtn.hidden = false;
      // Retry checkpoint cuma untuk error tahap analisis (sebelum segmen tampil)
      // yang resumable (bukan URL invalid/video privat/API key ditolak -- itu
      // pasti gagal lagi tanpa user memperbaiki sesuatu). Error render sudah
      // punya jalur retry sendiri (pilih ulang segmen + klik Render).
      if (retryBtn) {
        const canRetry =
          data.stage === "error" &&
          data.resumable !== false &&
          !segmentsSection.classList.contains("visible");
        retryBtn.hidden = !canRetry;
      }
      // Render berhenti (sukses atau gagal) -> tombol siap diklik lagi tanpa
      // user harus utak-atik checkbox dulu, supaya klip yang gagal bisa diulang.
      if (data.stage === "done" || data.stage === "error") {
        renderBtn.disabled = selected.size === 0;
      }
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
    if (retryBtn) retryBtn.hidden = true;
    downloadPreviewSection.classList.remove("visible");
    transcriptPreviewSection.classList.remove("visible");
    try {
      // Backend sidecar (PyInstaller onefile) bisa masih cold-start beberapa
      // detik setelah app dibuka; retry singkat sebelum mengaku gagal supaya
      // klik pertama tidak langsung "Failed to fetch".
      const maxAttempts = 10;
      let resp;
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
          resp = await fetch(`${API_BASE}/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ youtube_url: urlInput.value }),
          });
          break;
        } catch (err) {
          if (attempt === maxAttempts) throw err;
          setStatus("queued", "Menyiapkan backend, mencoba lagi...");
          await new Promise((r) => win.setTimeout(r, 1500));
        }
      }
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

  downloadContinueBtn.addEventListener("click", () => continueJob(downloadContinueBtn));
  transcriptContinueBtn.addEventListener("click", () => continueJob(transcriptContinueBtn));

  if (retryBtn) {
    retryBtn.addEventListener("click", async () => {
      retryBtn.disabled = true;
      try {
        const resp = await fetch(`${API_BASE}/jobs/${jobId}/retry`, { method: "POST" });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Retry gagal");
        retryBtn.hidden = true;
        startTimer();
        setStatus("queued");
        progressBar.value = 0;
        progressBar.classList.add("indeterminate");
      } catch (err) {
        setStatus("error", err.message);
      } finally {
        retryBtn.disabled = false;
      }
    });
  }

  openFolderBtn.addEventListener("click", () => {
    if (typeof window !== "undefined" && window.autoclip) {
      window.autoclip.openOutputFolder();
    }
  });

  const settingsApi = setupSettings(doc);
  // Jangan auto-jalan saat test (mockFetchQueue tiap test punya urutan sendiri);
  // Electron sungguhan selalu cek supaya user gak kejeblos gagal di tengah proses
  // karena API key belum diisi (lihat needsApiKeySetup).
  if (settingsApi && (!win.__AUTOCLIP_TEST__ || win.__AUTOCLIP_FORCE_API_KEY_CHECK__)) {
    settingsApi.checkApiKey();
  }
}

if (typeof module !== "undefined") {
  module.exports = { setupApp, formatTime, needsApiKeySetup };
}

if (typeof window !== "undefined" && window.document && !window.__AUTOCLIP_TEST__) {
  // Electron renderer: jalankan langsung.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupApp(document));
  } else if (document.getElementById("job-form")) {
    setupApp(document);
  }
}

// Provider aktif belum punya API key -> app tidak boleh dipakai dulu.
// cfg tanpa field llm_provider (bukan respons /config asli) -> jangan lock.
function needsApiKeySetup(cfg) {
  if (typeof cfg.llm_provider !== "string") return false;
  const keySet = cfg.llm_provider === "anthropic" ? cfg.anthropic_key_set : cfg.gemini_key_set;
  return !keySet;
}

function setupSettings(doc) {
  const section = doc.getElementById("settings-section");
  const form = doc.getElementById("settings-form");
  const openBtn = doc.getElementById("settings-btn");
  const closeBtn = doc.getElementById("settings-close");
  const backdrop = doc.getElementById("settings-backdrop");
  const statusEl = doc.getElementById("settings-status");
  const browseBtn = doc.getElementById("cfg-browse-dir");

  if (!section || !form) return null;

  let locked = false;

  function setStatus(text, type = "") {
    statusEl.textContent = text;
    statusEl.className = type ? type : "";
  }

  function open() {
    section.hidden = false;
    section.classList.add("visible");
    loadSettings();
  }

  function close() {
    if (locked) return;
    section.classList.remove("visible");
    section.hidden = true;
    setStatus("");
  }

  function applyLock(isLocked) {
    locked = isLocked;
    closeBtn.hidden = isLocked;
    const jobForm = doc.getElementById("job-form");
    if (jobForm) jobForm.hidden = isLocked;
  }

  async function checkApiKey() {
    try {
      const resp = await fetch(`${API_BASE}/config`);
      if (!resp.ok) return;
      const cfg = await resp.json();
      if (!needsApiKeySetup(cfg)) return;
      populate(cfg);
      section.hidden = false;
      section.classList.add("visible");
      applyLock(true);
      setStatus("Isi API key untuk mulai memakai AutoClip Lokal.", "");
    } catch {
      // Backend belum siap saat startup; job-form sendiri punya retry saat submit.
    }
  }

  openBtn.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("click", close);
  doc.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && section.classList.contains("visible")) close();
  });

  async function loadSettings() {
    setStatus("Memuat...", "");
    try {
      const resp = await fetch(`${API_BASE}/config`);
      if (!resp.ok) throw new Error("config error");
      const cfg = await resp.json();
      populate(cfg);
      setStatus("");
    } catch {
      setStatus("Gagal memuat pengaturan", "error");
    }
  }

  function populate(cfg) {
    const get = (name) => form.elements[name];
    const setValue = (name, value) => {
      const el = get(name);
      if (el) el.value = value ?? "";
    };
    const setChecked = (name, value) => {
      const el = get(name);
      if (el) el.checked = Boolean(value);
    };

    setValue("aspect_ratio", cfg.aspect_ratio);
    setValue("resolution", cfg.resolution);
    setValue("encoder", cfg.encoder);
    setValue("output_dir", cfg.output_dir);
    setChecked("subtitle_enabled", cfg.subtitle_enabled);
    setValue("subtitle_font_size", cfg.subtitle_font_size);
    setChecked("face_tracking_enabled", cfg.face_tracking_enabled);
    setValue("face_sample_fps", cfg.face_sample_fps);
    setValue("speaker_min_dwell_s", cfg.speaker_min_dwell_s);
    setValue("whisper_model", cfg.whisper_model);
    setValue("segment_count", cfg.segment_count);
    setValue("duration_min", cfg.duration_min);
    setValue("duration_max", cfg.duration_max);
    setValue("llm_provider", cfg.llm_provider);
    setValue("llm_model", cfg.llm_model);

    const geminiSet = doc.getElementById("gemini-key-set");
    if (geminiSet) geminiSet.hidden = !cfg.gemini_key_set;
    const anthropicSet = doc.getElementById("anthropic-key-set");
    if (anthropicSet) anthropicSet.hidden = !cfg.anthropic_key_set;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    setStatus("Menyimpan...", "");

    const data = {
      aspect_ratio: form.elements.aspect_ratio.value,
      resolution: parseInt(form.elements.resolution.value, 10),
      duration_min: parseInt(form.elements.duration_min.value, 10),
      duration_max: parseInt(form.elements.duration_max.value, 10),
      subtitle_enabled: form.elements.subtitle_enabled.checked,
      subtitle_font_size: parseInt(form.elements.subtitle_font_size.value, 10),
      face_tracking_enabled: form.elements.face_tracking_enabled.checked,
      face_sample_fps: parseInt(form.elements.face_sample_fps.value, 10),
      speaker_min_dwell_s: parseFloat(form.elements.speaker_min_dwell_s.value),
      whisper_model: form.elements.whisper_model.value,
      segment_count: parseInt(form.elements.segment_count.value, 10),
      llm_provider: form.elements.llm_provider.value,
      llm_model: form.elements.llm_model.value.trim(),
      encoder: form.elements.encoder.value,
      output_dir: form.elements.output_dir.value.trim(),
    };

    const geminiKey = form.elements.gemini_api_key.value.trim();
    if (geminiKey) data.gemini_api_key = geminiKey;
    const anthropicKey = form.elements.anthropic_api_key.value.trim();
    if (anthropicKey) data.anthropic_api_key = anthropicKey;

    // Hapus field kosong agar backend tidak menimpa nilai lama (terutama output_dir/model).
    if (!data.llm_model) delete data.llm_model;
    if (!data.output_dir) delete data.output_dir;

    try {
      const resp = await fetch(`${API_BASE}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.detail || "Save failed");
      populate(result);
      // Kosongkan input key supaya tidak tertinggal di DOM.
      form.elements.gemini_api_key.value = "";
      form.elements.anthropic_api_key.value = "";
      setStatus("Pengaturan tersimpan", "success");
      if (locked && !needsApiKeySetup(result)) {
        applyLock(false);
        close();
      }
    } catch (err) {
      setStatus(err.message || "Gagal menyimpan", "error");
    }
  });

  if (browseBtn) {
    browseBtn.addEventListener("click", async () => {
      if (typeof window !== "undefined" && window.autoclip && window.autoclip.selectOutputDir) {
        try {
          const dir = await window.autoclip.selectOutputDir();
          if (dir) form.elements.output_dir.value = dir;
        } catch {
          setStatus("Gagal memilih folder", "error");
        }
      } else {
        setStatus("Picker folder tidak tersedia", "error");
      }
    });
  }

  return { checkApiKey };
}
