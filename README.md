# AutoClip Lokal

![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)

Desktop app (Electron + Python/FastAPI) yang mengubah video YouTube panjang menjadi klip vertikal 9:16 siap upload, dengan subtitle otomatis dan pemilihan momen menarik berbantuan AI. Semua pemrosesan video berjalan lokal; hanya teks transkrip yang dikirim ke LLM API eksternal.

Dokumen lengkap: [PRD](docs/PRD_AutoClip_Lokal.docx) · [Arsitektur Teknis](docs/Arsitektur_Teknis_AutoClip_Lokal.docx) · [Task List TDD](docs/Task_List_TDD_AutoClip_Lokal.docx)

> Ganti `<owner>/<repo>` di badge di atas setelah repo ini didorong ke GitHub.

## Struktur Repo

```
autoclip-lokal/
├── electron-app/    # GUI desktop (Electron)
├── backend/         # Backend Python (FastAPI + pipeline)
├── tests/fixtures/  # Fixture audio/video/transkrip untuk test
└── docs/            # PRD, arsitektur, task list
```

## Setup Lokal

### Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
ruff check .
```

### Electron App
```bash
cd electron-app
npm install
npm test
npm run lint
```

### Pre-commit hook
```bash
cd backend && source .venv/bin/activate && cd ..
pre-commit install
```

## Konfigurasi

AutoClip menyimpan konfigurasi pengguna di file JSON lokal:

- **macOS/Linux:** `~/.autoclip/config.json`
- **Windows:** `%USERPROFILE%\.autoclip\config.json`
- Bisa dioverride via env `AUTOCLIP_CONFIG_DIR`

Buka panel **Pengaturan** di app untuk mengubah opsi; perubahan langsung berlaku untuk job berikutnya tanpa restart.

| Opsi | Deskripsi |
|------|-----------|
| Aspect ratio | `9:16`, `1:1`, `16:9`, `4:5` |
| Resolusi | `480p`, `720p`, `1080p` (short edge) |
| Durasi min/max | Rentang durasi klip yang dicari LLM (5–180 detik) |
| Subtitle | Aktifkan/nonaktifkan burn subtitle + ukuran font |
| Whisper model | `tiny`, `small`, `medium` |
| Jumlah segmen | Target kandidat highlight (1–20) |
| LLM provider | `gemini` atau `anthropic` |
| LLM model | Model spesifik; kosong = default provider |
| API key | Gemini/Anthropic key (disimpan lokal) |
| Encoder | `auto`, `libx264`, `h264_videotoolbox`, `h264_nvenc` |
| Folder output | Lokasi hasil render; kosong = `~/Movies/AutoClip` |

**Catatan keamanan MVP:** API key disimpan **plaintext** di JSON lokal. Ini sengaja untuk single-user localhost; file config hanya boleh diakses user sendiri. Untuk reset, hapus file `config.json` — app akan kembali ke default.

## Build & Packaging

Installer `.dmg` (macOS) dan `.exe` (Windows) dibangun dengan **Electron Builder**, dengan backend Python di-bundle sebagai executable sidecar lewat **PyInstaller**. `ffmpeg`/`ffprobe` static juga dibundle agar user akhir tidak perlu menginstal dependency tambahan.

### Requirement build
- Python 3.11+ dengan virtualenv yang sudah diinstall `requirements.txt` + `pyinstaller`
- Node.js 20+

### Perintah build lokal
```bash
cd electron-app
npm install

# Build backend sidecar + bundle ffmpeg, lalu buat installer
npm run dist

# Hanya build directory (tidak membuat installer) — lebih cepat untuk verifikasi
npm run dist:dir

# Verifikasi file wajib ada di output build
npm run verify:build
```

Output installer ada di `electron-app/dist/`:
- macOS: `dist/AutoClip Lokal-*.dmg`
- Windows: `dist/AutoClip Lokal Setup *.exe`

### Catatan
- Installer MVP **tidak di-sign/notarize**. Di macOS user perlu klik kanan "Open" saat pertama membuka.
- Model Whisper di-download saat pertama kali transcribe berjalan (tidak dibundle ke installer).
- CI membangun installer otomatis untuk macOS dan Windows serta menjalankan verifikasi manifest.
- API key Gemini ikut dibundle lewat `.env` saat build lokal. Ubah `.env` di root project sebelum `npm run dist` kalau key berubah.

## QA & Rilis

- Fase 10 (QA, Bug Bash & Rilis) telah menyelesaikan smoke test pipeline nyata dengan video publik.
- Semua test unit & integration lulus: ~200 pytest, 22 Jest, 3 Playwright E2E, 1 integration real-video.
- Known issues / keterbatasan MVP:
  - Beberapa video YouTube butuh JS runtime (Deno/Node) agar yt-dlp bisa mengekstrak semua format; app biasanya tetap bisa mengunduh video umum.
  - Waktu transkripsi pertama kali lebih lama karena download model Whisper (~150 MB).
  - Render menggunakan center-crop (belum deteksi wajah otomatis).
  - Installer unsigned: di macOS mungkin muncul peringatan Gatekeeper, pilih klik kanan → Open.

## Testing

Mengikuti pendekatan TDD (lihat `docs/Task_List_TDD_AutoClip_Lokal.docx`): unit test (pytest / Jest) sebagai porsi terbesar, integration test dengan dependency di-mock, dan smoke test end-to-end (Playwright) dijalankan manual/nightly.

Untuk smoke test pipeline nyata sebelum rilis:
```bash
cd backend
export GEMINI_API_KEY=$(grep -o 'GEMINI_API_KEY=.*' ../.env | cut -d= -f2-)
export PATH="../electron-app/build/backend/bin:$PATH"
.venv/bin/pytest -m integration tests/integration/test_pipeline_e2e.py -v
```
