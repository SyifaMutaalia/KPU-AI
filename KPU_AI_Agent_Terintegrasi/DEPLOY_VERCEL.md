# Deploy di Vercel

Aplikasi berjalan sebagai dua project Vercel yang terhubung ke repo GitHub ini; setiap push ke `main` men-deploy ulang keduanya.

| Project | Root Directory | URL |
| --- | --- | --- |
| `ai-agent-kpu` (Next.js) | `KPU_AI_Agent_Terintegrasi/kpu-ai-agent-nextjs` | https://ai-agent-kpu.vercel.app |
| `ai-agent-kpu-api` (FastAPI) | `KPU_AI_Agent_Terintegrasi` | https://ai-agent-kpu-api.vercel.app |

Komponen lain:

- **Database:** PostgreSQL Neon (`DATABASE_URL`), skema dibuat dengan `alembic upgrade head`.
- **Vector store:** Pinecone index `kpu-subang-rag`, namespace `kpu_jdih`.
- **n8n:** https://kpu-agent-syifa.duckdns.org (WF1 ingestion, WF2 error handler) memanggil backend publik.

## Environment variables

Frontend (`ai-agent-kpu`):

- `FASTAPI_BASE_URL=https://ai-agent-kpu-api.vercel.app`
- `APP_ORIGIN=https://ai-agent-kpu.vercel.app`

Backend (`ai-agent-kpu-api`): sama dengan `.env.example` dengan nilai produksi, antara lain `APP_ENV=production`, `COOKIE_SECURE=true`, `CORS_ORIGINS=["https://ai-agent-kpu.vercel.app"]`, `DATABASE_URL` (Neon), `SESSION_SECRET` acak, `OPENAI_*`, `PINECONE_*`, `INGESTION_CALLBACK_SECRET`, `ADMIN_RETRY_WEBHOOK_URL`, `ADMIN_RETRY_WEBHOOK_SECRET`, `N8N_API_URL`, `N8N_API_KEY`, `ADMIN_RESET_URL`.

`.vercelignore` di folder backend mencegah frontend, tes, dan data OCR ikut ter-bundle ke fungsi Python.

## Mengisi Pinecone pertama kali

```bash
python -m scripts.ingest_jdih_awal --pages 2 --backend https://ai-agent-kpu-api.vercel.app
```

Script ini setara dengan WF1 (teks asli PDF, chunk 1.000 karakter, metadata judul/status hukum dari JDIH) dan melaporkan setiap dokumen ke halaman admin. Setelah itu WF1 n8n mendeteksi dokumen baru setiap hari.

## Pemecahan masalah

- **"Origin tidak diizinkan"**: buka aplikasi lewat https://ai-agent-kpu.vercel.app, bukan URL preview.
- **Backend 500 saat start**: periksa log runtime project `ai-agent-kpu-api`; mode produksi menolak secret contoh dan cookie tidak aman.
