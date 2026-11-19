# Panduan Integrasi Next.js ↔ FastAPI ↔ LangChain (AI Agent KPU)

Isi paket:

- `app/`, `alembic/`, `scripts/` dan `requirements.txt` adalah **backend FastAPI/LangChain**.
- `kpu-ai-agent-nextjs/` adalah **frontend Next.js**, dengan `/api/*` sebagai proxy server-side ke FastAPI.
- DB aplikasi PostgreSQL (Neon atau service pada Compose EC2) menyimpan sesi, riwayat, akun admin, dan status operasional ingestion. **Pinecone** menyimpan indeks vektor dokumen.
- Admin Monitoring, WF2, instruksi helper callback WF1, bootstrap admin, konfigurasi, dan deployment Compose dijelaskan di [`ADMIN_MONITORING.md`](./ADMIN_MONITORING.md).

## PENTING: Keamanan kredensial

Di arsip yang kamu kirim sebelumnya, `.env.example` ternyata berisi string yang tampak seperti secret sungguhan. **Rotasi/replace password Neon, OpenAI API key, dan Pinecone API key di dashboard masing-masing**. Jangan menggunakan nilai lama. Paket hasil integrasi ini sudah menggantinya dengan placeholder. Jangan unggah `.env`, `.env.local`, atau connection string asli ke GitHub/ChatGPT.

## Langkah 1 — Persiapkan backend (PowerShell Windows)

Dari root folder ini (tempat file `requirements.txt`):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `.env` (jangan kirim ke orang lain):

- `DATABASE_URL`: connection string **Neon**. Jika dari Neon berawalan `postgresql://`, ubah hanya prefix menjadi `postgresql+psycopg://`. Simpan opsi SSL (`?sslmode=require`) dan opsi lain yang diberikan Neon. Jangan masukkan URL Neon ke Next.js.
- `SESSION_SECRET`: string rahasia baru acak minimal 32 karakter (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- `OPENAI_API_KEY`, `PINECONE_API_KEY` (baru, setelah rotasi), dan `PINECONE_INDEX_NAME`: isi sesuai dashboard.
- `CORS_ORIGINS=["http://localhost:3000"]`, `COOKIE_SECURE=false`, `COOKIE_SAMESITE=lax` untuk **localhost saja**.

Buat tabel Neon lewat migrasi **setelah memastikan DATABASE_URL benar**:

```powershell
alembic upgrade head
```

Jalankan FastAPI:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Cek `http://127.0.0.1:8000/health`, semestinya JSON `{"status":"ok",...}`.

## Langkah 2 — Jalankan Next.js di terminal PowerShell baru

```powershell
cd kpu-ai-agent-nextjs
Copy-Item .env.example .env.local
npm install
npm run dev
```

Buka `http://localhost:3000`. Isi frontend `.env.local`:

```
FASTAPI_BASE_URL=http://127.0.0.1:8000
APP_ORIGIN=http://localhost:3000
```

Gunakan URL frontend **http://localhost:3000**, bukan berganti-ganti antara `localhost` dan `127.0.0.1`, karena cookie memakai domain asal halaman.

## Langkah 3 — Tes koneksi API dan memory

1. Buka DevTools → Network, pastikan `GET /api/session` sukses dan cookie `kpu_session` tersimpan sebagai **HttpOnly**.
2. `GET /api/conversations` harus mengembalikan daftar, awalnya `[]` jika belum ada riwayat.
3. Kirim pesan `Halo` lewat UI. Next.js `POST /api/chat` mengirim `X-CSRF-Token` dan `conversation_id: null` ke FastAPI `POST /api/v1/chat`.
4. Setelah mendapat jawaban, kirim pertanyaan lanjutan. `conversation_id` sekarang dipakai ulang, sehingga backend mengambil riwayat dari Neon (hingga `MAX_CONTEXT_MESSAGES`).
5. Refresh halaman; pilih percakapan pada sidebar untuk mengembalikan pesan yang tersimpan.
6. Klik **Draf e-PPID**, isi kebutuhan informasi tanpa identitas pribadi, lalu buat/salin draf. Pengiriman resmi tetap dilakukan di e-PPID.

Catatan: `POST /api/chat` perlu konfigurasi OpenAI; untuk jawaban regulasi yang bersumber, Pinecone harus sudah berisi dokumen valid. Jika indeks belum siap, agent harus abstain, bukan mengarang isi pasal. Ingestion PDF 585 dokumen belum dilakukan oleh paket ini. Parser pasal-utuh masih pekerjaan berikutnya.

## Troubleshooting

| Gejala | Penyebab umum | Periksa |
|---|---|---|
| 502 di `/api/session` atau `/api/chat` | FastAPI tidak hidup/URL salah | FastAPI port 8000; `FASTAPI_BASE_URL` |
| 403 CSRF | Sesi belum diinisialisasi, token salah, atau host berubah | Refresh; pakai `localhost:3000` konsisten; cek cookie HttpOnly |
| 503 Layanan AI | Key OpenAI/Pinecone belum valid atau layanan error | Periksa variabel `.env` backend dan log server tanpa mencetak secret |
| `database` error | DB URL/Neon password/migrasi tidak sesuai | `DATABASE_URL`, status Neon dan `alembic upgrade head` |
| Belum ada sumber | Dokumen belum di-ingest/metadata tidak valid | Ingestion dokumen dan `RAG_ALLOWED_HOSTS` |
| Riwayat hilang | Cookie sesi terhapus/expired, atau browser beda | Sesi anonim tidak sama dengan akun login |

## Deploy dengan aman

- Production FastAPI wajib HTTPS, `COOKIE_SECURE=true`, `APP_ENV=production`, dan storage PostgreSQL Neon.
- Untuk deployment Next.js dan FastAPI di domain berbeda, pendekatan BFF Next.js ini tetap menerbitkan cookie untuk domain Next.js. Pastikan `APP_ORIGIN` sama dengan URL frontend dan server FastAPI hanya menerima trafik dari lapisan yang diizinkan (perlu proteksi upstream/edge, bukan hanya CORS).
- Rate limiting per sesi anonim tidak cukup untuk publik; tambahkan rate limiting berbasis IP/edge dan monitoring biaya.
- Jangan mengklaim sistem aman untuk produksi tanpa audit, pengujian isolasi sesi, dependensi, dan deployment.

## Versi framework

Starter awal menggunakan `next@15.2.4`, yang sudah memiliki advisori keamanan. Paket integrasi menargetkan **Next.js 15.5.18 + React 19.2.6**, sesuai rilis keamanan Next.js Mei 2026; sebelum deployment jalankan `npm audit` dan pastikan versi patch masih didukung. Referensi: https://vercel.com/changelog/next-js-may-2026-security-release
