# KPU AI Agent — Next.js (terhubung ke FastAPI)

Frontend Next.js 15 memakai **same-origin Backend-for-Frontend (BFF)**: browser → Next.js `/api/*` → FastAPI `/api/v1/*` → LangChain + Pinecone + Neon. Hanya Next.js yang memiliki `FASTAPI_BASE_URL`. Rahasia OpenAI/Neon/Pinecone hanya berada di `.env` backend FastAPI, **tidak pernah di `NEXT_PUBLIC_*`**.

## Jalankan secara lokal

1. Hidupkan FastAPI di port 8000 (lihat `../CARA_MENJALANKAN.md`).
2. Salin `.env.example` menjadi `.env.local` pada folder frontend.
3. `npm install`
4. `npm run dev`
5. Buka `http://localhost:3000`.

## API Next.js proxy

- `GET /api/session` → FastAPI `GET /api/v1/session`: HttpOnly cookie diteruskan melalui `Set-Cookie`, token CSRF melalui JSON.
- `POST /api/chat` → `POST /api/v1/chat`: mengirim `{message, conversation_id}` dan `X-CSRF-Token`.
- `GET /api/conversations` → daftar riwayat untuk sesi pemilik.
- `GET/DELETE /api/conversations/:id` → melihat/menghapus riwayat milik pemegang sesi.
- `POST /api/eppid/draft` → penyusunan teks draf copy-ready.

Pengguna tanpa login hanya dapat membuka riwayat selama cookie sesi masih tersedia. **Tidak ada pemulihan lintas perangkat tanpa autentikasi.**

Lihat `../CARA_MENJALANKAN.md` untuk detail keamanan, deployment, dan troubleshooting.
