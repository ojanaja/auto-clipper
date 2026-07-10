# Task List — Fitur Konfigurasi In-App (AutoClip Lokal)

Rencana kerja TDD untuk menambahkan panel **Settings** di aplikasi: user bisa mengatur konfigurasi output klip (rasio, resolusi, durasi, subtitle), model proses (Whisper, jumlah segmen), provider LLM + API key, dan encoder — tanpa mengedit env/kode.

Referensi arsitektur: config disimpan sebagai **file JSON lokal per instalasi** (bukan DB server). PRD non-func: sediakan opsi resolusi lebih rendah untuk preview cepat.

## Prinsip kerja (ikuti konvensi repo)

- **TDD Red → Green → Refactor** per task. Tulis test yang gagal dulu, implementasi seminim mungkin, rapikan.
- Backend: `pytest` + `pytest-mock`. Frontend: `Jest` + `@testing-library/dom` (jsdom).
- Lint wajib lolos: `ruff check .` (backend), `npm run lint` (electron-app). Pre-commit hook menjalankan keduanya.
- Bahasa pesan UI/error: Indonesia. Nama fungsi/variabel: English, ikuti gaya modul sekitar.
- Dependency pipeline harus tetap **injectable** supaya bisa di-mock (lihat `PipelineOrchestrator`).
- Jangan turunkan coverage inti (< 80% pada logic non-I/O).

## Definition of Done keseluruhan fitur

- [x] `GET /config` & `PUT /config` jalan, persist ke JSON lokal, validasi input.
- [x] Rasio/resolusi/durasi/subtitle/model/provider/key/encoder benar-benar dipakai pipeline (bukan cuma disimpan).
- [x] API key **tidak** pernah dikembalikan mentah oleh `GET /config` (hanya flag `*_key_set`).
- [x] Panel Settings di Electron: load config saat buka, simpan via `PUT`, validasi ringan, feedback sukses/gagal.
- [x] Semua test unit lama tetap lulus (default config = perilaku sekarang: 9:16, 1080p, subtitle on, whisper small, provider gemini).
- [x] Smoke test e2e happy-path masih hijau.

---

## Skema Konfigurasi (`AppConfig`)

| Field | Tipe | Default | Valid | Dipakai di |
|---|---|---|---|---|
| `aspect_ratio` | str | `"9:16"` | `9:16`, `1:1`, `16:9`, `4:5` | reframe crop + render scale |
| `resolution` | int | `1080` | `480`, `720`, `1080` | render output dims |
| `duration_min` | int | `20` | 5–180, `< duration_max` | prompt LLM |
| `duration_max` | int | `60` | 5–180, `> duration_min` | prompt LLM |
| `subtitle_enabled` | bool | `true` | — | render (skip filter `ass` bila false) |
| `subtitle_font_size` | int | `80` | 24–160 | `generate_ass` |
| `whisper_model` | str | `"small"` | `tiny`, `small`, `medium` | transcribe |
| `segment_count` | int | `8` | 1–20 | prompt LLM (hint jumlah kandidat) |
| `llm_provider` | str | `"gemini"` | `gemini`, `anthropic` | `make_llm_client` |
| `llm_model` | str | `""` | bebas (kosong = default provider) | `make_llm_client` |
| `gemini_api_key` | str | `""` | — (sensitif) | `make_llm_client` |
| `anthropic_api_key` | str | `""` | — (sensitif) | `make_llm_client` |
| `encoder` | str | `"auto"` | `auto`, `libx264`, `h264_videotoolbox`, `h264_nvenc` | render `-c:v` |
| `output_dir` | str | `""` | path (kosong = default `~/Movies/AutoClip`) | app.py render output |

**Aturan API key (keamanan):**
- Disimpan plaintext di JSON lokal (single-user, localhost-only — batasan MVP, dokumentasikan di README).
- `GET /config` **tidak** mengembalikan `gemini_api_key`/`anthropic_api_key`; kembalikan `gemini_key_set: bool` & `anthropic_key_set: bool`.
- `PUT /config`: field key hanya diperbarui bila dikirim **non-kosong**; kosong/absen = pertahankan key lama (jangan hapus tak sengaja).

**Turunan dimensi output** (`AppConfig.output_dimensions() -> (w, h)`):
- `ratio = ALLOWED_RATIOS[aspect_ratio]` (w/h). Short edge = `resolution`.
- Portrait/square (`ratio <= 1`): `w = resolution`, `h = round(resolution / ratio)`.
- Landscape (`ratio > 1`): `h = resolution`, `w = round(resolution * ratio)`.
- Bulatkan `w`, `h` ke **genap** (syarat encoder).
- Contoh: `9:16 @ 1080` → `(1080, 1920)`; `16:9 @ 720` → `(1280, 720)`; `1:1 @ 1080` → `(1080, 1080)`.

---

## Fase A — Backend: model config + persistence

### A1. `AppConfig` dataclass + validasi + turunan dimensi
- **File:** `backend/config.py`, test `backend/tests/unit/test_config.py`
- **Red:** test `AppConfig` default sesuai tabel; `output_dimensions()` untuk beberapa rasio/resolusi (genap); `target_ratio()`; validasi menolak `aspect_ratio`/`resolution`/`whisper_model`/`llm_provider`/`encoder` di luar himpunan (raise `ConfigError`); `duration_min < duration_max` diklaim/di-clamp; `from_dict` mengabaikan key tak dikenal & mengisi default untuk yang hilang.
- **Green:** dataclass + `ALLOWED_*` set + `from_dict`/`to_dict` + `output_dimensions`/`target_ratio` + `validate()`.
- **DoD:** cover ~100% (pure logic). `ConfigError(Exception)` khusus, bukan generik.

### A2. Load/save JSON + path resolusi
- **File:** `backend/config.py` (lanjutan), test sama.
- **Red:** `default_config_path()` hormati env `AUTOCLIP_CONFIG_DIR` (default `~/.autoclip/config.json`); `load_config(path)` → file tak ada = default; file ada = merge default + isi file (key hilang → default, key asing → diabaikan); `save_config(cfg, path)` menulis JSON valid + `mkdir` parent; round-trip `save` lalu `load` menghasilkan config setara.
- **Green:** implementasi baca/tulis JSON dengan `pathlib`.
- **DoD:** file korup/JSON invalid → fallback ke default (log peringatan), tidak crash.

### A3. Serialisasi publik (tanpa key mentah)
- **File:** `backend/config.py`, test sama.
- **Red:** `to_public_dict()` tidak memuat `gemini_api_key`/`anthropic_api_key`; memuat `gemini_key_set`/`anthropic_key_set` sesuai kosong/tidak; memuat semua field non-sensitif.
- **Green:** implementasi `to_public_dict`.
- **DoD:** grep memastikan tak ada key mentah bocor.

---

## Fase B — Backend: endpoint `GET`/`PUT /config`

### B1. `GET /config`
- **File:** `backend/app.py`, test `backend/tests/unit/test_config_api.py`
- **Red:** `GET /config` → 200 + body = `to_public_dict()` config saat ini; default saat file belum ada; tidak memuat key mentah.
- **Green:** endpoint baca `load_config()`.
- **DoD:** test lolos tanpa file config nyata (pakai `AUTOCLIP_CONFIG_DIR=tmp_path` via monkeypatch/env).

### B2. `PUT /config`
- **File:** `backend/app.py`, test sama.
- **Red:** `PUT /config` dengan partial body memperbarui field valid, menyimpan, mengembalikan `to_public_dict()`; field key kosong tidak menghapus key lama; field key non-kosong memperbarui (verifikasi `*_key_set` berubah); input invalid (mis. `aspect_ratio: "3:2"`, `duration_min > duration_max`) → 422/400 dengan pesan jelas; field tak dikenal diabaikan.
- **Green:** endpoint merge → `validate` → `save_config`. Pydantic model `ConfigUpdate` (semua optional) untuk parsing.
- **DoD:** transisi key set/unset benar; error validasi actionable.

---

## Fase C — Backend: wiring config ke pipeline

Semua parametrize dengan **default = perilaku sekarang** supaya test lama tetap hijau.

### C1. `compute_crop_box` parametrik rasio
- **File:** `backend/pipeline/reframe.py`, test `test_reframe.py`
- **Red:** `compute_crop_box(frame_w, frame_h, faces, target_ratio=9/16)`; test crop untuk rasio `1:1`, `16:9`, `4:5` (crop box benar, tetap di dalam frame, dimensi genap); default tetap 9:16 (test lama tak berubah).
- **Green:** ganti konstanta `_TARGET_RATIO` jadi parameter.
- **DoD:** test reframe lama + kasus rasio baru lolos.

### C2. `generate_ass` parametrik font size
- **File:** `backend/pipeline/subtitle.py`, test `test_subtitle.py`
- **Red:** `generate_ass(words, segment_start, font_size=80)`; test font size custom muncul di style ASS; default 80 → golden file lama tetap sama.
- **Green:** inject font size ke header style.
- **DoD:** golden-file test lama lolos (default), test font custom lolos.

### C3. `render_segment` parametrik output + subtitle + encoder
- **File:** `backend/pipeline/render.py`, test `test_render.py`
- **Red:**
  - Signature baru (keyword-only, default = sekarang):
    `render_segment(..., progress_cb=None, target_ratio=9/16, out_width=1080, out_height=1920, subtitle=True, subtitle_font_size=80, encoder="auto")`.
  - Test: `scale={out_width}:{out_height}` sesuai param; crop pakai `target_ratio`; `subtitle=False` → tidak ada `ass=` di `-vf` (dan tidak menulis file `.ass`); `encoder="libx264"` → `-c:v libx264` di command, `encoder="auto"` → tanpa `-c:v` (biarkan ffmpeg default); default keseluruhan tetap hasilkan command lama (`crop=606:1080:657:0`, `scale=1080:1920`).
- **Green:** susun `-vf` kondisional + tambah `-c:v` bila encoder != auto.
- **DoD:** semua test render lama + baru lolos; progress per-detik tetap jalan.

### C4. `build_prompt` / `find_highlights` parametrik durasi + jumlah
- **File:** `backend/pipeline/highlight.py`, test `test_highlight.py`
- **Red:** `build_prompt(words, duration_min=20, duration_max=60, count=8)` → prompt memuat rentang durasi & target jumlah; `find_highlights(words, client, ..., duration_min, duration_max, count)` teruskan ke prompt; default tetap seperti sekarang.
- **Green:** interpolasi param ke template prompt.
- **DoD:** test parsing lama tetap lolos; test prompt memuat angka konfigurasi.

### C5. `make_llm_client` dari config (provider + key + model)
- **File:** `backend/pipeline/llm_client.py`, test `test_llm_client.py`
- **Red:** `make_llm_client(provider=None, gemini_key=None, anthropic_key=None, model=None)`; provider `anthropic` → `AnthropicLLMClient` dengan key/model; provider `gemini` → `GeminiLLMClient`; key kosong → fallback ke env (kompat lama); key salah/absen untuk provider terpilih → `RuntimeError` pesan jelas (arahkan isi di Settings).
- **Green:** perluas factory; argumen override env.
- **DoD:** test factory lama (env-based) tetap lolos.

### C6. Orchestrator baca config tiap run
- **File:** `backend/orchestrator.py`, test `test_orchestrator.py`
- **Red:**
  - `PipelineOrchestrator(..., config_provider=load_config)` (injectable; default `load_config`).
  - `run_analysis`: panggil `transcribe_fn` dengan `whisper_model` dari config; bangun LLM client via `make_llm_client(provider/keys/model dari config)` bila `llm_client` tak di-inject; `highlight_fn` dapat `duration_min/max`, `count`.
  - `run_render`: hitung `out_width/out_height` via `config.output_dimensions()`, `target_ratio`, `subtitle_enabled`, `subtitle_font_size`, `encoder`; teruskan ke `render_fn`.
  - Test pakai `config_provider=lambda: AppConfig(aspect_ratio="1:1", resolution=720, ...)` dan verifikasi argumen yang diteruskan ke `render_fn`/`transcribe_fn`/`highlight_fn`.
- **Green:** load config di awal tiap method, teruskan bit relevan.
- **DoD:** test orchestrator lama (default config) tetap lolos; test config custom memverifikasi propagasi.

### C7. `output_dir` dari config di endpoint render
- **File:** `backend/app.py`, test `test_render_api.py`
- **Red:** `POST /jobs/{id}/render` pakai `config.output_dir` bila diisi, else default `~/Movies/AutoClip`; test memverifikasi path output mengikuti config.
- **Green:** resolve output dir dari config sebelum spawn `run_render`.
- **DoD:** test lama (default) lolos; test output_dir custom lolos.

---

## Fase D — Frontend: panel Settings (Electron renderer)

### D1. Tombol gear + panel/modal Settings
- **File:** `electron-app/src/renderer/index.html` (markup + CSS design-system dark), `src/renderer/app.js`, test `electron-app/tests/settings.test.js`
- **Red (jsdom):** tombol `#settings-btn` di header; klik → panel `#settings-panel` `visible`; tombol tutup menyembunyikan; panel punya field untuk tiap config (select rasio, select resolusi, number durasi min/max, toggle subtitle, number font, select whisper, number segmen, select provider, input `llm_model`, input password key gemini & anthropic, select encoder, input output_dir).
- **Green:** markup + toggle visibility. Ikuti gaya CSS existing (tokens `--color-*`, radius, spacing, focus ring, `prefers-reduced-motion`).
- **DoD:** aksesibilitas dasar: label tiap field, focusable, min tap target.

### D2. Load config saat panel dibuka
- **File:** `src/renderer/app.js`, test sama.
- **Red:** buka panel → `GET /config` dipanggil; field terisi dari respons; field key ditampilkan sebagai kosong dengan indikator "tersimpan" bila `*_key_set` true (jangan tampilkan key mentah).
- **Green:** fetch + populate. Gunakan `FakeWebSocket`/`mockFetchQueue` pattern yang sudah ada di `tests/helpers.js`.
- **DoD:** tidak menaruh key mentah ke DOM.

### D3. Simpan config (`PUT`) + feedback
- **File:** `src/renderer/app.js`, test sama.
- **Red:** klik "Simpan" → `PUT /config` dengan body dari field; field key hanya dikirim bila diisi (biarkan key lama bila kosong); sukses → pesan "Tersimpan"; error validasi → tampilkan pesan dari backend; validasi ringan klien (durasi min < max) sebelum kirim.
- **Green:** kumpulkan form → `PUT` → handle respons.
- **DoD:** test happy-path + error path lolos.

### D4. (Opsional) Aksi bergantung config
- Sembunyikan/disable tombol render bila provider terpilih belum ada key (`*_key_set` false) dengan pesan arahkan ke Settings. Cukup 1 test.

---

## Fase E — Integrasi, dokumen, verifikasi

### E1. Smoke test e2e (Playwright, manual)
- **File:** `electron-app/e2e/settings.spec.js`
- Buka app → buka Settings → ubah rasio jadi `1:1` & resolusi `720` → Simpan → tutup. (Tanpa render nyata; cukup verifikasi panel + persist via backend dev.)

### E2. Integration test pipeline mocked dengan config custom
- **File:** `backend/tests/integration/` (mocked, bukan real video)
- Orchestrator dengan `config_provider` rasio `16:9` → verifikasi `render_fn` menerima `out_width/out_height` landscape.

### E3. Dokumentasi
- Update `README.md`: bagian "Konfigurasi" — lokasi file `~/.autoclip/config.json`, daftar opsi, catatan API key plaintext lokal, cara reset (hapus file).
- Update dokumen arsitektur (bagian Config & Secrets) bila perlu.

### E4. Verifikasi akhir
- [x] `cd backend && pytest && ruff check .`
- [x] `cd electron-app && npm test && npm run lint`
- [x] `npm run e2e` (happy-path + settings smoke)
- [x] Commit per fase (A–E), pesan `feat: ...`, pre-commit hijau.

---

## Catatan & jebakan

- **Kompat mundur:** semua param baru pipeline harus punya default = perilaku sekarang; kalau ada test lama gagal, kemungkinan default salah.
- **Encoder `auto`:** jangan set `-c:v` sama sekali (biarkan ffmpeg pilih libx264). Hardware encoder (`h264_videotoolbox`/`nvenc`) bisa gagal di device tanpa dukungan → tangani error render per klip (sudah ada mekanisme: satu klip gagal tak hentikan lainnya).
- **Rasio horizontal (16:9):** subjek crop bisa terlihat beda; center-crop tetap fallback. Deteksi wajah tetap out-of-scope (lihat ponytail comment di `render.py`).
- **API key di log:** pastikan tak ada `print`/log yang membocorkan key (backend maupun renderer). `GET /config` sudah dimasking; jaga juga jangan echo di pesan error.
- **Re-baca config tiap run**, bukan cache di startup — supaya perubahan Settings langsung berlaku untuk job berikutnya tanpa restart app.
