# Task List — Auto Face-Tracking (Reframe Mengikuti Speaker)

Rencana kerja TDD untuk mengganti center-crop statis dengan **crop yang mengikuti speaker aktif** (podcast/talk/vlog). Fondasi sudah ada dari Fase 5.

## Keputusan desain (dipilih)

- **Policy crop:** follow **1 speaker aktif** — pilih wajah yang mulutnya paling banyak bergerak antar-sample (indikasi sedang bicara); fallback ke wajah terbesar/tengah bila ambigu atau hanya 1 wajah; fallback center-crop bila tak ada wajah.
- **Detektor:** **YuNet** (`cv2.FaceDetectorYN`, ONNX, CPU) — akurasi bagus, tanpa dependency mediapipe. Memberi bbox + 5 landmark (2 mata, hidung, 2 sudut mulut).
- **Terapkan crop:** **ffmpeg expression** — crop dinamis `x(t)`/`y(t)` piecewise-linear, tetap **single-pass** (crop → scale → subtitle) seperti sekarang. Tak perlu decode/encode frame-by-frame di Python.

## Fondasi yang sudah ada (jangan tulis ulang)

Di `backend/pipeline/reframe.py`:
- `BBox(x, y, w, h)` — bounding box wajah.
- `CropBox(x, y, w, h)`.
- `compute_crop_box(frame_w, frame_h, faces, target_ratio=9/16)` — crop box dari daftar bbox; kosong → center-crop. **Setelah task config C1**, sudah menerima `target_ratio`.
- `smooth_crop_boxes(boxes, window=5)` — moving-average anti-jitter pada x/y.

Yang **belum** ada: deteksi wajah nyata, pemilihan speaker aktif, pembangun jalur crop per-waktu, penerapan crop dinamis di ffmpeg.

## Ketergantungan

- Idealnya dikerjakan **setelah** `Task_List_Konfigurasi_AutoClip.md` fase C1 (`compute_crop_box` sudah parametrik `target_ratio`) dan C3 (`render_segment` sudah menerima `out_width/out_height/target_ratio`). Bila belum, kerjakan C1/C3 dulu.
- Tambah dependency: `opencv-python` (YuNet ada di modul `cv2`), model `face_detection_yunet_2023mar.onnx`.

## Prinsip kerja (ikuti konvensi repo)

- **TDD Red → Green → Refactor** per task. `pytest` + `pytest-mock`; ruff wajib lolos; pre-commit hijau.
- **Logic murni diuji 100%** (scoring speaker, pembangun jalur crop, pembangun expression). Deteksi/model I/O di-**mock** di unit test; validasi nyata di integration test bertanda `@pytest.mark.integration`.
- Semua fitur di belakang flag config `face_tracking_enabled` (default bisa `true` atau `false` — lihat fase E). **Default OFF dulu** agar test lama & perilaku existing tidak berubah sampai fitur matang.
- Performa: **jangan** decode seluruh video di Python. Sample low-fps, hanya rentang segmen.

## Definition of Done keseluruhan

- [x] Klip podcast 2 orang: crop mengikuti orang yang sedang bicara, perpindahan halus (tak jitter, tak lompat tiap detik).
- [x] Tanpa wajah (gameplay/slide) → center-crop (perilaku sekarang), tak crash.
- [x] Single-pass ffmpeg tetap (crop dinamis + scale + subtitle dalam satu command).
- [x] Bisa dimatikan via config → jatuh ke center-crop statis lama.
- [x] Model YuNet ter-bundle/di-download saat pertama kali (didokumentasikan, seperti model Whisper).
- [x] Semua test lama lulus; test baru (unit + integration) hijau.

---

## Fase A — Modul deteksi wajah (YuNet, sampled)

### A1. Loader model + resolusi path
- **File:** `backend/pipeline/face_detect.py`, test `backend/tests/unit/test_face_detect.py`
- **Red:** `yunet_model_path()` hormati env `AUTOCLIP_YUNET_MODEL`, else default `~/.autoclip/models/face_detection_yunet_2023mar.onnx`; `ensure_model()` mengunduh bila belum ada (mock `urllib`/`httpx` di test, verifikasi URL + tulis file); model sudah ada → tak download ulang.
- **Green:** implementasi path + download idempోten.
- **DoD:** test tanpa jaringan (download di-mock).

### A2. `Detection` dataclass + skala koordinat
- **File:** `face_detect.py`, test sama.
- **Red:** `Detection(bbox: BBox, landmarks: dict, score: float)`; helper `_scale_detection(det, scale_x, scale_y)` mengubah koordinat dari frame sampel (dikecilkan) ke resolusi sumber; landmark `mouth_left`/`mouth_right` ikut terskala.
- **Green:** dataclass + scaling murni.
- **DoD:** pure function, cover penuh.

### A3. `detect_faces_sampled` (sampling + deteksi)
- **File:** `face_detect.py`, test sama.
- **Red:** `detect_faces_sampled(video_path, start, end, fps=2, detector=None) -> list[tuple[float, list[Detection]]]`; test dengan **fake detector + fake VideoCapture** (mock `cv2.VideoCapture`) memverifikasi: hanya frame dalam [start,end] disample; interval waktu ~1/fps; hasil per-timestamp; koordinat terskala balik; frame tanpa wajah → list kosong pada timestamp itu.
- **Green:** buka video, seek, ambil frame tiap 1/fps, resize untuk deteksi cepat, panggil `FaceDetectorYN.detect`, skala balik.
- **DoD:** tak decode seluruh video (verifikasi hanya frame sample yang dibaca). `detector` injectable untuk test.

---

## Fase B — Pemilihan speaker aktif (logic murni)

### B1. Skor "sedang bicara" via gerak area mulut
- **File:** `backend/pipeline/speaker.py`, test `backend/tests/unit/test_speaker.py`
- **Red:** `mouth_region(det) -> BBox` (kotak sekitar mulut dari landmark `mouth_left/right` + tinggi proporsional bbox); `mouth_motion_score(prev_patch, cur_patch) -> float` (mis. mean abs diff piksel grayscale ternormalisasi). Test dengan patch sintetik: patch identik → skor ~0; patch berbeda → skor tinggi.
- **Green:** implementasi murni (numpy).
- **DoD:** cover penuh; ternormalisasi 0..1 agar ambang stabil.

### B2. Pilih wajah aktif per waktu + fallback
- **File:** `speaker.py`, test sama.
- **Red:** `select_active_face(detections, motion_scores) -> Detection | None`:
  - 0 wajah → `None`.
  - 1 wajah → wajah itu.
  - ≥2 wajah → wajah dengan `motion_score` tertinggi bila selisih di atas ambang; bila di bawah ambang (tak jelas siapa bicara) → wajah **terbesar/paling tengah** (deterministik).
  Test: dua wajah, satu skor jauh lebih tinggi → terpilih; skor mirip → pilih terbesar; input kosong → None.
- **Green:** implementasi kebijakan.
- **DoD:** deterministik, tanpa I/O.

### B3. Hysteresis anti-ganti-cepat
- **File:** `speaker.py`, test sama.
- **Red:** `apply_speaker_hysteresis(timeline, min_dwell_s=1.5) -> timeline` — cegah crop lompat bolak-balik antar speaker: pertahankan pilihan sekarang minimal `min_dwell_s` sebelum boleh pindah. Test: urutan pilihan A,B,A,B cepat → jadi stabil (A bertahan) sampai dwell lewat.
- **Green:** state machine sederhana atas timeline (list waktu→face-id/None).
- **DoD:** pure; parametrik `min_dwell_s`.

---

## Fase C — Bangun jalur crop (logic murni)

### C1. Timeline deteksi → jalur CropBox
- **File:** `backend/pipeline/crop_path.py`, test `backend/tests/unit/test_crop_path.py`
- **Red:** `build_crop_path(frame_w, frame_h, active_timeline, target_ratio) -> list[tuple[float, CropBox]]`:
  - Tiap entri waktu: wajah aktif → `compute_crop_box(frame_w, frame_h, [bbox], target_ratio)`; None → `compute_crop_box(..., [])` (center).
  - Terapkan `smooth_crop_boxes` pada urutan CropBox.
  Test: input timeline sintetik → jalur benar, ter-smooth, semua crop dalam frame, w/h konstan (hanya x/y bergerak).
- **Green:** rangkai `compute_crop_box` + `smooth_crop_boxes` (keduanya sudah ada).
- **DoD:** memanfaatkan fungsi Fase 5; w/h konstan sepanjang klip.

### C2. Kurangi titik redundan (opsional, hemat expr)
- **File:** `crop_path.py`, test sama.
- **Red:** `simplify_path(path, min_delta_px=6) -> path` — buang titik yang x/y-nya nyaris sama dengan sebelumnya (di bawah ambang) supaya expression ffmpeg lebih pendek. Test: jalur datar → tersisa sedikit titik; jalur bergerak → titik penting dipertahankan.
- **Green:** filter greedy.
- **DoD:** tak mengubah bentuk gerakan signifikan.

---

## Fase D — Crop dinamis di ffmpeg (expression)

### D1. Pembangun expression piecewise-linear
- **File:** `backend/pipeline/render.py` (atau helper `crop_expr.py`), test `test_render.py`/`test_crop_expr.py`
- **Red:** `build_crop_x_expr(path, clip_start) -> str` dan `build_crop_y_expr(...)`:
  - Waktu relatif klip `t' = t - clip_start`.
  - Bentuk: penjumlahan segmen `between(t,ti,ti1)*lerp(xi,xi1,(t-ti)/(ti1-ti))` + clamp ujung (`gte(t,tlast)*xlast`, `lt(t,t0)*x0`).
  - Gunakan builtin ffmpeg expr: `between`, `lerp`, `gte`, `lt`. Bulatkan nilai, clamp x ke `[0, frame_w-crop_w]`.
  Test: path 2–3 titik → string memuat `between(` & `lerp(`; nilai di titik ujung benar (evaluasi manual sederhana pada substring, atau parse angka).
- **Green:** hasilkan string.
- **DoD:** ekspресi valid secara sintaks ffmpeg (uji nyata di integration D3).

### D2. Wire ke `render_segment` (mode dinamis)
- **File:** `render.py`, test `test_render.py`
- **Red:** `render_segment(..., crop_path=None)`:
  - `crop_path=None` → perilaku sekarang (crop statis dari `compute_crop_box`, single box).
  - `crop_path` diberikan → `-vf` pakai `crop=w:h:x='<expr>':y='<expr>'` (w/h dari path/config), lalu `scale`, lalu `ass`. Verifikasi command memuat `crop=` dengan `x='...between...'`.
  - Tetap single-pass; progress per-detik tetap jalan.
- **Green:** susun filter kondisional.
- **DoD:** test statis lama lolos (default `crop_path=None`); test dinamis memverifikasi expr masuk `-vf`.

### D3. Integration nyata (marker)
- **File:** `backend/tests/integration/test_face_tracking_real.py`
- **Red:** `@pytest.mark.integration`, skip di CI reguler: pakai klip pendek nyata (fixture atau download 1 video publik ber-wajah), jalankan deteksi → path → render; assert file `.mp4` valid & bisa di-probe, durasi sesuai. (Visual dicek manual.)
- **DoD:** menghasilkan klip yang crop-nya bergerak; tak crash pada klip tanpa wajah.

---

## Fase E — Config + orchestrator + fallback

### E1. Field config face-tracking
- **File:** `backend/config.py` (lihat `Task_List_Konfigurasi_AutoClip.md`), test config.
- **Red:** tambah field: `face_tracking_enabled: bool = False`, `face_sample_fps: int = 2` (1–5), `speaker_min_dwell_s: float = 1.5`. Validasi rentang.
- **Green:** tambah ke `AppConfig` + validasi.
- **DoD:** default OFF → perilaku existing.

### E2. Orchestrator: bangun crop_path bila enabled
- **File:** `backend/orchestrator.py`, test `test_orchestrator.py`
- **Red:** di `run_render`, bila `config.face_tracking_enabled`:
  1. `detect_faces_sampled(video, seg.start, seg.end, fps=config.face_sample_fps)`
  2. skor mulut + `select_active_face` per waktu + `apply_speaker_hysteresis`
  3. `build_crop_path(...)` → teruskan `crop_path` ke `render_fn`.
  Bila disabled → `crop_path=None` (jalur lama).
  Semua fungsi deteksi/seleksi **injectable** (default implementasi nyata) supaya test pakai stub. Test: enabled → `render_fn` menerima `crop_path` non-None hasil stub; disabled → `None`.
- **Green:** rangkai; tangani error deteksi → fallback center (log peringatan, jangan gagalkan klip).
- **DoD:** kegagalan deteksi satu klip → fallback center, klip lain lanjut (mekanisme per-klip sudah ada).

### E3. Toggle di panel Settings (frontend)
- **File:** `electron-app/src/renderer/*`, test `settings.test.js`
- **Red:** toggle "Auto face-tracking" + input sample fps + dwell di panel Settings; termuat dari `GET /config`, terkirim via `PUT /config`.
- **Green:** tambah field (ikut pola dari task list config fase D).
- **DoD:** test load/save field baru.

---

## Fase F — Packaging, performa, dokumen

### F1. Bundle/So model YuNet
- **File:** `electron-app/scripts/*` (build), README.
- Tambah langkah: unduh `face_detection_yunet_2023mar.onnx` saat build atau saat pertama run (seperti model Whisper). Dokumentasikan lokasi + ukuran.

### F2. Guard performa
- Batasi `face_sample_fps` (default 2). Resize frame sebelum deteksi (mis. lebar 640) lalu skala balik. Ukur waktu deteksi per klip; bila > ambang, turunkan fps otomatis (opsional).

### F3. Dokumentasi
- README: bagian "Auto Face-Tracking" — cara aktifkan di Settings, batasan (podcast statis paling bagus, gameplay/slide fallback center), catatan model.
- Update dokumen arsitektur (modul reframe) bila perlu.

### F4. Verifikasi akhir
- [x] `cd backend && pytest && ruff check .`
- [x] Bug render ulang dari status DONE diperbaiki (re-render valid, all-fail -> ERROR).
- [ ] Integration face-tracking manual lolos pada 1 video nyata (visual OK).
- [x] `cd electron-app && npm test && npm run lint`
- [ ] Commit per fase (A–F), pesan `feat: ...`, pre-commit hijau.

---

## Catatan & jebakan

- **Jitter vs responsif:** `smooth_crop_boxes` window besar = halus tapi lambat merespons pindah speaker; kecil = responsif tapi goyang. Tuning `window` + `min_dwell_s` bareng.
- **Speaker ambigu:** kalau dua orang sama-sama diam/bicara, jatuh ke wajah terbesar/tengah — hindari crop bolak-balik.
- **Skala koordinat:** deteksi di frame kecil (640px) → **wajib** skala bbox & landmark balik ke resolusi sumber sebelum `compute_crop_box`.
- **Ekspресi ffmpeg:** panjang tumbuh dengan jumlah titik → pakai `simplify_path`. Uji builtin `lerp`/`between` benar-benar tersedia di build ffmpeg yang di-bundle (Fase 9). Kalau tidak, ganti ke rangkaian `if(between(...),...)`.
- **Clamp x/y:** crop tak boleh keluar frame; `compute_crop_box` sudah clamp per titik, tapi expression hasil `lerp` antar titik juga harus aman (kedua ujung sudah di-clamp → interpolasi di antaranya juga dalam batas karena w/h konstan).
- **Default OFF:** rilis awal biarkan center-crop; nyalakan face-tracking sebagai opt-in sampai terbukti stabil pada beragam video.
- **Out of scope v1:** split-screen 2 wajah, deteksi speaker berbasis audio, tracking objek non-wajah. Catat sebagai roadmap.
