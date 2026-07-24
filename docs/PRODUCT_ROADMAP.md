# AutoClip — Roadmap Produk (Clone 1:1 "AutoClip v4.4.5 Tura Turu")

> **Status:** Planning · **Tujuan:** Bangun produk komersil setara aplikasi referensi, dikerjakan bertahap per fase, tiap fase _production-ready_.
> **Dokumen ini adalah sumber kebenaran roadmap.** Update tiap fase selesai — centang deliverable, catat perubahan keputusan.

---

## 1. Ringkasan Eksekutif

App saat ini (**AutoClip Lokal**) adalah pipeline single-job: URL YouTube → unduh → transkrip → analisis AI (highlight) → render klip vertikal (subtitle burn-in + face tracking). Satu view, tanpa tab.

Aplikasi referensi (**AutoClip v4.4.5 Tura Turu**) adalah produk matang komersil dengan **4 tab** dan layer monetisasi. Target: capai paritas fitur 1:1, lalu jual sebagai produk.

Gap-nya besar — bukan cuma nambah tombol, tapi 4 subsistem mayor + infrastruktur produk (signing, update, lisensi, payment). Karena itu dikerjakan **bertahap**, tiap fase berdiri sendiri dan _production-ready_ sebelum lanjut.

---

## 2. Keputusan Arsitektur (LOCKED)

Keputusan berikut sudah difinalisasi dan mengunci arah kerja berbulan-bulan. Ubah hanya dengan alasan kuat, dan catat perubahannya di sini.

| # | Keputusan | Pilihan | Alasan / Konsekuensi |
|---|-----------|---------|----------------------|
| D1 | **Model pemrosesan** | Lokal (whisper + ffmpeg di mesin user) + cloud tipis (lisensi/credit) | Sesuai nama "Lokal" & referensi. Processing berat gratis di mesin user; server cuma buat billing. |
| D2 | **Autopost** | Browser automation (Playwright + Chrome asli, cookies.txt fallback) | Persis referensi. Jalan di semua platform, no app-review. **Trade-off diterima:** rapuh (rusak tiap platform ganti UI), lawan ToS platform, maintenance tinggi, risiko ban akun user. Lihat §9. |
| D3 | **Lisensi + Payment** | SaaS — **LemonSqueezy** (Merchant of Record) | Handle license-key, aktivasi, pajak, refund otomatis. Integrasi tipis di client. Alternatif dipertimbangkan: Keygen, Gumroad. |
| D4 | **Frontend shell** | Electron + vanilla JS, tab nav (Klip / Kustomisasi / Thumbnail / Autopost) | Lanjut stack existing, hindari rewrite. Tab shell diperkenalkan di Fase 1. |
| D5 | **Preview canvas** | CSS approximation client-side (live, draggable); render final tetap ffmpeg server-side (akurat) | Persis referensi. Thumbnail preview = server-rendered (butuh akurasi efek). |

---

## 3. Dua Track Paralel

Menjual produk = bukan cuma clone UI. Ada 2 track:

### Track A — Fitur (mirror referensi)
Kustomisasi → Thumbnail → Batch grid → Autopost

### Track B — Productization (bikin bisa dijual, tak terlihat di screenshot tapi wajib)
- **Code signing** (Azure Trusted Signing) — hapus "Unknown Publisher", wajib produk berbayar
- **Auto-update** (electron-updater + release server)
- **Lisensi + credit backend** (LemonSqueezy) — angka "42" di referensi = credit server-side
- **Payment** (via LemonSqueezy)
- **Crash reporting / telemetry**

Track B sering diremehkan tapi menentukan apakah app bagus bisa jadi produk. Fitur dulu (validasi), monetisasi pas mau launch — **kecuali signing (Fase 0) dikerjakan awal** karena dibutuhkan semua distribusi.

---

## 4. Definisi "Production Ready"

Sebuah fase **belum selesai** sampai memenuhi checklist ini:

- [ ] Test lengkap: unit + integrasi + e2e (Playwright) hijau
- [ ] Error handling + pesan error **bahasa Indonesia** yang jelas untuk user
- [ ] Build ter-**sign**, lolos Windows SmartScreen
- [ ] Jalan mulus di Windows mid-range (bukan cuma mesin dev) — uji di spek target
- [ ] Perf ter-ukur & tercatat (mis. render X menit di CPU tanpa GPU)
- [ ] Lint bersih (ruff + eslint + prettier)
- [ ] Changelog + dokumentasi singkat fitur
- [ ] Tidak merusak fitur fase sebelumnya (regresi = blocker)

---

## 5. Roadmap Ringkas

| Fase | Isi | Effort | Risiko | Blok pada |
|------|-----|:------:|:------:|-----------|
| **0** | Signing + auto-update | S | Rendah | User bikin akun Azure Trusted Signing |
| **1** | Kustomisasi (style engine + canvas live) | L | Rendah | — |
| **2** | Thumbnail generator | M | Rendah | Fase 1 (reuse canvas/preview) |
| **3** | Batch Klip grid (reshape workflow) | L | Sedang | Fase 1 (kustomisasi dipakai per klip) |
| **4** | Autopost (browser automation) | XL | Tinggi | Fase 3 (queue klip) |
| **5** | Lisensi + credit + payment (gerbang jual) | L | Sedang | LemonSqueezy account + Fase 1–4 stabil |

Effort: S=kecil, M=sedang, L=besar, XL=sangat besar. Tanpa timeline kalender (santai per fase); label effort untuk urutan & ekspektasi.

---

## 6. Detail Fase

### Fase 0 — Signing + Auto-update `[S, Rendah]`

**Tujuan:** installer ter-sign (no "Unknown Publisher") + user dapat update otomatis.

- Azure Trusted Signing (~$10/bln, verifikasi identitas) → config `win.certificateFile`/env `CSC_LINK`+`CSC_KEY_PASSWORD` di [electron-builder.yml](../electron-app/electron-builder.yml)
- electron-updater + release feed (GitHub Releases privat / server sendiri)
- **Deliverable:** installer signed lolos SmartScreen; app cek & pasang update sendiri.
- **Blok:** user harus buat akun Azure Trusted Signing (aksi & biaya user). Bisa jalan paralel dengan Fase 1.

---

### Fase 1 — Kustomisasi `[L, Rendah]`

Fase pertama yang dikerjakan (kode). Sekalian memperkenalkan **app shell / tab nav** karena app sekarang cuma 1 view.

Referensi tab **Kustomisasi**: toggle Aktifkan, Impor/Ekspor/Reset preset, section collapsible dengan dot on/off:
Subtitle · Overlay Sumber · Watermark · Overlay Gambar · Color Grade. Plus canvas live 720×1280 draggable.

Dipecah jadi sub-milestone, tiap sub shippable + tested:

| Sub | Isi | Deliverable |
|-----|-----|-------------|
| **1a** ✅ | App shell + tab nav (Klip/Kustomisasi/Thumbnail/Autopost) + model config kustomisasi + persistence (`backend/customization.py`, terpisah dari `config.py` supaya bisa diimpor/ekspor mandiri) + Impor/Ekspor/Reset preset JSON | Selesai 2026-07-24. Tab jalan, preset save/load via `GET/PUT /customization` + `POST /customization/reset`, Impor/Ekspor lewat dialog file Electron (IPC). Section (Subtitle/Overlay Sumber/Watermark/Overlay Gambar/Color Grade) baru flag enabled, belum ada efek render. |
| **1b** ✅ | Subtitle template system — 6 template (Karaoke Pop, Hormozi, Neon Glow, TikTok Bold, Word Punch, Clean) + LANJUTAN (font/size/align/opasitas/warna teks·outline·shadow/kotak latar/posisi) → generate ASS + wire ke render | Selesai 2026-07-24. Template preset (di frontend, single source of truth) + field advanced tersimpan lewat `PUT /customization` (merge per-field). `generate_ass`/`render_segment`/orchestrator terima `SubtitleStyle` opsional — `style=None` = perilaku lama byte-identik (gated: cuma aktif kalau `customization.enabled && subtitle.enabled`). Live preview CSS approximation (bukan draggable — drag interaktif dijadwalkan Fase 1e saat canvas gabungan semua overlay dibangun). |
| **1c** ✅ | Color Grade — preset (Tidak Ada/Cinematic/Hangat/Dingin/Cerah/Film/Mono) + manual slider (kontras/terang/saturasi/gamma/suhu/vignette) → ffmpeg filter chain | Selesai 2026-07-24. Filter native ffmpeg (`eq`, `colortemperature`, `vignette`) diverifikasi tersedia di build lokal sebelum dipakai. Filter cuma disisipkan kalau nilainya bukan default (identity) — preset "Tidak Ada"/slider netral = video tak disentuh sama sekali. Preview CSS: `filter: contrast()/saturate()/brightness()` di layer background terpisah dari teks subtitle (grade tak boleh ikut ke teks, sama seperti render asli — grade sebelum burn-in). |
| **1d** ✅ | Overlay: Gambar (logo, size/opasitas/rotate), Watermark (teks ghost), Overlay Sumber (kredit) → ffmpeg filter + drag position | Selesai 2026-07-24. Overlay Gambar lewat `filter_complex` dua-input (`scale`→`format=rgba`→`colorchannelmixer` opasitas→`rotate` transparan→`overlay` posisi persen dipusatkan) + `-shortest` (gambar di-loop tanpa EOF, wajib dibatasi). Watermark/Overlay Sumber ternyata TIDAK pakai `drawtext` (filter itu tak ada di build ffmpeg lokal — cuma `ass`/libass yang tersedia) — direalisasi ulang sebagai event ASS statis (override tag `\pos\fn\fs\1c\1a\frz`) digabung ke file `.ass` yang sama dengan subtitle karaoke, satu filter `ass=` saja. Field posisi (pos_x/pos_y persen) sudah ada lewat input angka — drag interaktif di canvas tetap dijadwalkan Fase 1e. |
| **1e** | Canvas 720×1280 full composite (drag semua overlay, x/y%) + polish + full test pass + changelog | Tab Kustomisasi lengkap, production-ready |

**Catatan teknis:**
- Reuse [subtitle.py](../backend/pipeline/subtitle.py) & [render.py](../backend/pipeline/render.py) — extend, jangan tulis ulang
- Color grade: native ffmpeg `eq` (kontras/terang/saturasi/gamma), `colortemperature` (suhu), `vignette`. **No dependency baru.**
- Subtitle template: generate ASS style + efek `\k` (karaoke), highlight box (Word Punch), glow (border+shadow) — extend generator ASS existing
- Overlay: `overlay` filter (gambar) + `rotate`; watermark/sumber via ASS (bukan `drawtext` — filter itu butuh libfreetype, tak tersedia di build ffmpeg lokal; `ass`/libass sudah wajib dipakai buat subtitle jadi reuse itu)
- Preview canvas = CSS approximation (D5); final = ffmpeg

---

### Fase 2 — Thumbnail Generator `[M, Rendah]`

Tab terpisah, generator thumbnail per klip. **Canvas beda** (1080×1920). Self-contained, tak menyentuh pipeline utama.

Referensi: template (MrBeast, Bold Outline, Glow Pop, Boxed, Minimal), teks AI 2–5 kata per klip (editable), highlight (mis. "kata terakhir" warna beda), stroke/shadow/glow/gradient fill/accent bar/kotak latar, color grade **terpisah** (kontras/saturasi/ketajaman/vignette). **Pratinjau di-render server-side** (biar efek & grade akurat).

- Ambil 1 frame representatif dari klip → komposit teks + efek server-side pakai **Pillow** (bukan ffmpeg `drawtext` — filter itu tak tersedia di build ffmpeg dev lokal, lihat §9 risiko)
- Teks AI ringkas: reuse [llm_client.py](../backend/pipeline/llm_client.py) untuk generate 2–5 kata
- **Deliverable:** tab Thumbnail, template + editor teks, preview server-rendered, output tersimpan per klip.

---

### Fase 3 — Batch Klip Grid `[L, Sedang]`

Reshape workflow single-job → grid banyak klip sekaligus. Frontend-heavy.

Referensi tab **Klip**: mode AI Otomatis vs Manual; toggle inline (Face Track, Subtitle, Landscape Fit, Sumber, Watermark); hasil grid banyak card (mis. 30) — tiap card: thumbnail preview (judul burned-in), rentang waktu, checkbox "Render klip ini", edit judul/teks-thumbnail/caption via ikon pensil, preview 1:1 (render sekali → cache), "Buka Folder". Bulk: Pilih semua/Kosongkan, dropdown "Setelah selesai", Render terpilih/semua.

- Backend sudah punya segments; tambah: per-segment metadata (judul/caption/thumbnail-text edit), cache preview 1:1
- Frontend: grid card + editor per card + state seleksi + bulk actions
- Kustomisasi (Fase 1) & Thumbnail (Fase 2) dipakai per klip di sini
- **Deliverable:** workflow batch penuh, preview cache, edit per klip, render selektif.

---

### Fase 4 — Autopost `[XL, Tinggi]`

**Fitur terberat & terapuh.** Browser automation upload ke sosmed. Subsistem sendiri.

Referensi tab **Autopost**: antrean klip siap-post + impor folder klip lama; multi-akun (YouTube, Meta FB+IG, dll) — login via Chrome asli (login manual, sesi disimpan), fallback import cookies.txt saat CAPTCHA; template metadata judul/caption/hashtag dengan placeholder `{title}` `{caption}` `{date}` `{duration_sec}`; visibilitas (Publik/dll); retry count; mode browser (1 Chrome stabil vs multi-Chrome paralel); jadwal (sekarang/terjadwal); riwayat upload.

- Playwright (Python atau Node) drive Chrome persisten per akun
- Session store per akun + cookies.txt import fallback
- Per platform: adapter upload sendiri (YT Shorts, IG Reels, FB) — **titik rapuh utama**
- Scheduler + retry + antrean + riwayat (perlu persistence)
- **Deliverable:** multi-akun, upload otomatis, jadwal, retry, riwayat.
- **Risiko:** lihat §9. Butuh maintenance berkelanjutan.

---

### Fase 5 — Lisensi + Credit + Payment `[L, Sedang]`

Gerbang monetisasi. Aktifkan sebelum launch.

- LemonSqueezy: produk + license key + checkout (handle pajak/refund/MoR)
- Client: aktivasi license (validasi via LemonSqueezy API) + cache offline grace period
- Credit system (angka "42"): definisikan **apa yang makan credit** (render? autopost? per klip?) — perlu diputus (§10)
- "Traktir" (donasi) opsional
- **Deliverable:** user bisa beli → aktivasi → pakai; credit ter-track; build ter-gate lisensi.

---

## 7. Gap Analysis — Sekarang vs Referensi

| Area | App sekarang | Referensi | Fase |
|------|-------------|-----------|:----:|
| Pipeline inti (download→transkrip→AI→render) | ✅ Ada | ✅ | — |
| Subtitle burn-in | ✅ Fixed style | ✅ 6 template + advanced | 1b |
| Face tracking / reframe | ✅ Ada | ✅ | — |
| Tab navigation | ❌ Single view | ✅ 4 tab | 1a |
| Color grade | ❌ | ✅ preset + manual | 1c |
| Overlay gambar/watermark/sumber | ❌ | ✅ | 1d |
| Preset import/export | ❌ | ✅ | 1a |
| Live canvas draggable | ❌ | ✅ | 1e |
| Thumbnail generator | ❌ | ✅ tab sendiri | 2 |
| Batch grid banyak klip | ❌ Single job | ✅ grid + edit per klip | 3 |
| Autopost multi-akun | ❌ | ✅ | 4 |
| Credit / lisensi / payment | ❌ | ✅ | 5 |
| Code signing / auto-update | ❌ | ✅ (implisit produk) | 0 |

---

## 8. Tech Stack (ringkas)

- **Backend:** Python, FastAPI, PyInstaller (packaged). Pipeline: yt-dlp (download), faster-whisper (transkrip), LLM (highlight), ffmpeg (render), face detect + reframe.
- **Frontend:** Electron + vanilla JS (single `index.html` + `app.js`), WebSocket progress.
- **Tambahan per fase:** Playwright (Fase 4), electron-updater + Azure Trusted Signing (Fase 0), LemonSqueezy SDK/API (Fase 5).
- **Prinsip:** reuse existing, native ffmpeg/stdlib dulu, **no dependency baru kecuali perlu** (ponytail).

---

## 9. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| **Autopost rapuh** — platform ganti UI, automation rusak | Fitur mati, user komplain | Adapter per-platform terisolasi; cookies.txt fallback; retry; monitor & patch cepat; changelog jujur |
| **ToS platform** — automation lawan ToS, akun user bisa ke-ban | Liability ke user berbayar | Disclaimer jelas di app; cookies user sendiri; jangan mass-spam; rate limit wajar. **Keputusan bisnis user (D2).** |
| **Whisper/ffmpeg berat di mesin low-end** | Render lama, user kecewa | Perf test di spek target; opsi model whisper kecil; estimasi waktu di UI |
| **Retrofit lisensi mahal** kalau ditunda | Rework arsitektur | Desain hook credit/lisensi ringan sejak Fase 1 (flag, belum enforce) |
| **Scope creep 1:1** | Tak kelar-kelar | Fase ketat, tiap fase shippable, jangan lompat |
| **ffmpeg dev lokal (Homebrew biasa) tak punya libass/libfreetype** — `ass`, `subtitles`, `drawtext` semua "Unknown filter" (ketauan pas Fase 1d) | Subtitle/watermark/sumber silent no-op di mesin dev (warning di stderr, video tetap jalan tanpa teks); Fase 2 Thumbnail yang rencananya opsi `drawtext` juga kena | Render dev di-tes lewat mock (`_ass_filter_available` di-patch true) + verifikasi command-line manual pakai filter yang independen (scale/format/colorchannelmixer/rotate/overlay). Sebelum rilis: pastikan ffmpeg static yang dibundle PyInstaller/Electron Builder (lihat README §Build) genuinely dicompile dengan `--enable-libass --enable-libfreetype`, jangan asumsi. Fase 2 Thumbnail: pakai Pillow buat teks, bukan `drawtext`, biar tak bergantung ketersediaan filter yang sama. |

---

## 10. Open Items (perlu diputus, belum blok fase awal)

- **Credit model:** apa yang makan credit? (per render / per autopost / per klip / bulanan) — diputus sebelum Fase 5, tapi hook-nya disiapkan Fase 1.
- **Platform autopost mana saja** di v1? (YouTube + Meta cukup, atau + TikTok?) — pengaruh Fase 4.
- **Harga & paket** (one-time vs subscription vs credit pack) — pengaruh Fase 5.
- **Azure Trusted Signing account** — aksi user, mulai kapan saja.
- **Landscape Fit & mode Manual** (toggle di tab Klip referensi) — masuk Fase 3, detail belum di-spec.

---

## 11. Log Perubahan Keputusan

| Tanggal | Perubahan |
|---------|-----------|
| 2026-07-24 | Dokumen dibuat. Locked: D1–D5. Mulai dari Fase 1 (kode) + Fase 0 (paralel, aksi user). |
| 2026-07-24 | Fase 1a selesai: app shell + tab nav, `customization.py` (model+persistence terpisah dari `config.py`), endpoint `/customization` (GET/PUT/reset), IPC impor/ekspor preset JSON. 294/295 backend test pass (1 gagal pra-eksisting, tak terkait), 44/45 jest pass, 3/3 e2e pass, ruff+eslint+prettier bersih. Lanjut ke 1b (subtitle template). |
| 2026-07-24 | Fase 1b selesai: `SubtitleStyleConfig` extended (template+font+size+align+opacity+4 warna+outline/shadow width+kotak latar+posisi) + `validate()`; `pipeline/subtitle.py` dapat `SubtitleStyle` dataclass + `_hex_to_ass_color` + `generate_ass(..., style=None)` yang byte-identik ke output lama saat `style=None` (regression-proof via `test_generate_ass_without_style_unchanged_from_before`); orchestrator gate render pakai style kustom cuma kalau `customization.enabled && subtitle.enabled` lewat `_build_subtitle_style`. Frontend: template gallery 6 tombol + fieldset Lanjutan + preview CSS approximation (posisi/warna/opacity/outline/shadow/kotak-latar live). 339/340 backend test pass (1 pra-eksisting tak terkait), 50/51 jest pass, ruff+eslint+prettier bersih. Proses `AutoClip Lokal.app` lama (2 hari, nahan port 8237) dimatikan atas izin user — verifikasi e2e visual jalan penuh pakai backend segar setelahnya. Ketemu & fix 1 bug nyata dari situ: outline/shadow width preview dipakai mentah tanpa discale ke ukuran canvas preview (168px vs render asli 1080px) → teks jadi blob gak kebaca di font kecil; fix pakai `PREVIEW_SCALE=1/5` konsisten dgn scaling font, + test regresi baru. Lanjut ke 1c (Color Grade). |
| 2026-07-24 | Fase 1c selesai: `ColorGradeConfig` extended (preset+kontras+terang+saturasi+gamma+suhu+vignette) + `validate()`; modul baru `pipeline/color_grade.py` (`ColorGradeStyle` + `build_color_grade_filters` — native ffmpeg `eq`/`colortemperature`/`vignette`, dicek dulu ketersediaannya via `ffmpeg -filters` sebelum dipakai; filter di-skip kalau nilai default, jadi "Tidak Ada" preset = video tak difilter sama sekali). Wired ke `render_segment` (filter disisipkan sebelum subtitle burn-in) & orchestrator (gate `customization.enabled && color_grade.enabled`, sama pola dgn subtitle_style). Frontend: preset gallery 7 tombol + 6 slider + preview canvas 2-layer (bg CSS filter + vignette radial-gradient overlay, teks subtitle di layer terpisah tak ikut ke-grade). 379/380 backend test pass (1 pra-eksisting tak terkait), 54/55 jest pass, ruff+eslint+prettier bersih, e2e 3/3 pass dgn backend segar. Ketemu & fix 1 bug CSS nyata: tombol preset Color Grade (`.kustom-grade-btn`) gak punya style sendiri, jatuh ke default `button` biru polos — fix dgn share class `.kustom-template-btn` (sama seperti tombol template Subtitle), diverifikasi computed-style (filter/gradient/active-class semua sudah benar dari awal, cuma CSS visualnya yg kelewat). Lanjut ke 1d (Overlay: Gambar/Watermark/Sumber). |
| 2026-07-24 | Fase 1d selesai: `TextOverlayConfig` (base class field text/font/size/color/opacity/pos_x/pos_y/rotate) diturunkan jadi `OverlaySumberConfig` & `WatermarkConfig` (default beda: sumber di bawah-tengah opaque, watermark ghost tengah-diagonal `-30°`/opacity 25%); `OverlayGambarConfig` (image_path/size/opacity/rotate/pos_x/pos_y). Temuan penting sebelum implementasi: `ffmpeg -filters` di build lokal (Homebrew `ffmpeg` polos, bukan `ffmpeg-full`) TERNYATA tak punya `drawtext` maupun `ass`/`subtitles` sama sekali (formula Homebrew biasa gak compile libfreetype/libass) — beda dari asumsi sesi sebelumnya yang cuma tervalidasi lewat mock test, gak pernah dites ffmpeg sungguhan. Konsekuensi desain: Watermark/Overlay Sumber TIDAK pakai `drawtext`, direalisasi sebagai event ASS statis (durasi penuh klip, override tag `\pos\fn\fs\bord0\shad0\1c\1a\frz`) digabung ke file `.ass` yang sama dgn subtitle karaoke (modul baru `pipeline/overlay.py`: `build_text_overlay_event`), jadi cuma satu filter `ass=` yang dipasang — konsisten reuse infrastruktur subtitle yang sudah ada, sama-sama gated di belakang `_ass_filter_available()`. Overlay Gambar butuh input kedua (`-loop 1 -i gambar`) → `render_segment` dapat cabang `-filter_complex` (scale→format=rgba→colorchannelmixer opacity→rotate transparan `c=black@0.0`→overlay posisi persen dipusatkan) dipakai HANYA kalau image_overlay diisi & filenya ada, kalau tidak tetap jalur `-vf` lama persis (byte-identik, zero risk). Filter (`scale`/`format`/`colorchannelmixer`/`rotate`/`overlay`) diverifikasi manual end-to-end lewat ffmpeg asli sebelum dipakai (bikin video+gambar dummy, jalanin command penuh, screenshot 1 frame buat cek posisi/rotasi/opacity kebentuk benar). Ketemu & fix 1 bug produksi nyata dari verifikasi manual itu: gambar `-loop 1` gak pernah EOF, dan tanpa `-shortest` proses ffmpeg jalan TANPA BATAS (baru ketauan setelah proses makan CPU 445% selama 15 menit) — fix dengan nambah flag `-shortest` biar durasi output ngikut input tersingkat (video utama yang sudah dipotong `-ss/-to`). Frontend: section Watermark/Overlay Sumber (field teks/font/ukuran/warna/opasitas/rotasi/posisi, builder `textOverlayFields()` dipakai bareng krn bentuknya identik) + Overlay Gambar (tombol "Pilih Gambar" via IPC `select-overlay-image` baru + slider ukuran/opasitas/rotasi + posisi), preview canvas dapat 3 layer baru (`#kustom-preview-image`, `#kustom-preview-watermark`, `#kustom-preview-overlay_sumber`) dgn CSS `rotate()`/opacity/positioning yang match 1:1 semantik ffmpeg (dipusatkan di titik pos, gambar pakai `width:%` relatif canvas jadi otomatis proporsional tanpa perlu PREVIEW_SCALE manual kayak teks). 441/442 backend test pass (1 pra-eksisting tak terkait), 62/63 jest pass, ruff+eslint+prettier bersih. Verifikasi visual e2e manual (bukan otomatis — screenshot Playwright throwaway) sempat ketemu 1 lagi kelas bug: assertion `toHaveText("Tersimpan")` di skrip tes lolos VAKUM krn teks status sama dgn state sebelumnya (gak berubah antar 2 save sukses berturutan) → nyamar seakan-akan field teks ke-reset sendiri padahal itu murni salah sinkronisasi di skrip tes, bukan bug app (dibuktikan pakai `page.waitForResponse` per-PUT eksplisit, root cause di-trace sampai ketemu lewat property-setter override buat nangkep siapa yang nulis `el.value`). App-nya sendiri terbukti benar: reload tab & baca ulang dari `GET /customization` menunjukkan teks watermark/sumber persist dgn tepat. Field posisi drag interaktif tetap dijadwalkan Fase 1e (canvas gabungan). Lanjut ke 1e (Canvas full composite + polish + full test pass). |
