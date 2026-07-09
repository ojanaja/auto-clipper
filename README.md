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

## Testing

Mengikuti pendekatan TDD (lihat `docs/Task_List_TDD_AutoClip_Lokal.docx`): unit test (pytest / Jest) sebagai porsi terbesar, integration test dengan dependency di-mock, dan smoke test end-to-end (Playwright) dijalankan manual/nightly.
