# Deploy frontend ke Vercel

Vercel hanya menjalankan **frontend Next.js** (`kpu-ai-agent-nextjs`). Backend FastAPI, PostgreSQL, dan n8n tetap berjalan di EC2 (Docker Compose di `infra/`). Browser hanya berbicara dengan Vercel; route `/api/*` Next.js meneruskan permintaan ke FastAPI dari sisi server.

## 1. Buka backend ke internet (EC2)

Server Vercel harus bisa menjangkau FastAPI lewat HTTPS.

1. Buat DNS `A` record untuk domain backend (mis. `api-kpu-syifa.duckdns.org`) ke IP EC2.
2. Tambahkan ke `infra/.env`:
   ```
   API_HOST=api-kpu-syifa.duckdns.org
   VERCEL_ORIGIN=https://<nama-project>.vercel.app
   ```
   `VERCEL_ORIGIN` = domain **produksi** Vercel, tanpa `/` di akhir. Nilai ini ditambahkan ke `CORS_ORIGINS` backend dan dipakai untuk link reset password.
3. Terapkan:
   ```bash
   cd infra
   docker compose build kpu-backend
   docker compose up -d
   curl https://api-kpu-syifa.duckdns.org/health
   ```

Tanpa `API_HOST`/`VERCEL_ORIGIN`, konfigurasi sama persis seperti sebelumnya.

## 2. Project Vercel

- **Root Directory:** `KPU_AI_Agent_Terintegrasi/kpu-ai-agent-nextjs`
- **Framework Preset:** Next.js (build/output default)
- **Environment Variables** (Production):
  - `FASTAPI_BASE_URL=https://api-kpu-syifa.duckdns.org`
  - `APP_ORIGIN=https://<nama-project>.vercel.app` (harus sama dengan `VERCEL_ORIGIN`)

Jangan menambahkan prefix `NEXT_PUBLIC_` pada variabel tersebut.

## 3. Periksa setelah deploy

1. Buka halaman utama, kirim satu pertanyaan chat.
2. Buka `/admin/login`, login, lalu buka Dashboard, Workflows, Documents, dan Errors.
3. Jika muncul **"Origin tidak diizinkan"**: `APP_ORIGIN` (Vercel) dan `VERCEL_ORIGIN` (EC2) tidak sama persis dengan URL yang dibuka di browser. Gunakan domain produksi, bukan URL preview `*-git-*.vercel.app`.
4. Jika muncul **"FastAPI tidak bisa dihubungi"**: cek `FASTAPI_BASE_URL` dan `curl https://API_HOST/health`.
