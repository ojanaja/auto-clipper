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

## Testing

Mengikuti pendekatan TDD (lihat `docs/Task_List_TDD_AutoClip_Lokal.docx`): unit test (pytest / Jest) sebagai porsi terbesar, integration test dengan dependency di-mock, dan smoke test end-to-end (Playwright) dijalankan manual/nightly.
