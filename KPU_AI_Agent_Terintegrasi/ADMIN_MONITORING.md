# Admin monitoring dan penanganan error

Fitur admin memakai FastAPI, SQLAlchemy/Alembic, PostgreSQL, dan Next.js BFF yang sudah ada. Chat, riwayat, draf e-PPID, RAG, index, namespace, dan chunking Pasal tidak diubah. Tidak ada registrasi publik.

## Halaman dan endpoint

- `/admin/login`, `/admin/forgot-password`, `/admin/reset-password`
- `/admin/dashboard`, `/admin/dashboard/workflows`, `/admin/dashboard/documents`, `/admin/dashboard/errors`
- `/admin/change-password` untuk kata sandi bootstrap yang wajib diganti
- API: `/api/v1/admin/auth/*`, `/api/v1/admin/dashboard/{summary,workflows,documents,errors}`, `/api/v1/admin/dashboard/errors/{id}/retry`, dan callback internal ingestion

Dashboard membaca PostgreSQL. Jumlah chunk/Pasal hanya ditampilkan jika tercatat dan hanya dihitung dari dokumen dengan `pinecone_confirmed=true`. Status dokumen PostgreSQL dan konfirmasi Pinecone ditampilkan terpisah. Data kosong tetap kosong; tidak ada seed data dashboard.

## Monitoring langsung n8n

Dashboard menampilkan seluruh workflow aktif/nonaktif dan 100 eksekusi terbaru dari n8n REST API. Halaman Workflow n8n dan status koneksi pada halaman admin lain menggunakan endpoint backend yang membutuhkan sesi admin. Backend hanya melakukan `GET` ke `/api/v1/workflows` dan `/api/v1/executions?includeData=false`; detail input/output execution, token, dan kredensial tidak dikirim ke browser. Operasi mengaktifkan, menghentikan, mengubah, atau menjalankan workflow tidak tersedia. Retry tetap memakai webhook khusus terautentikasi yang tercatat/audited.

Setelah membuat API key n8n secara privat, isi `N8N_API_KEY` pada environment backend dan `N8N_API_URL`. Di Docker Compose EC2, default internalnya `http://n8n:5678`; untuk deployment terpisah, gunakan URL n8n yang dapat dicapai backend. Berikan akun/key akses baca ke seluruh project yang memang perlu dimonitor dan seminimal mungkin; endpoint aplikasi sendiri hanya memakai `GET`, tetapi batas otorisasi key tetap mengikuti konfigurasi n8n. Jangan masukkan API key pada frontend, workflow export, chat, atau repositori. Jika API belum dikonfigurasi atau tidak dapat dihubungi, halaman menampilkan status/error dan metrik PostgreSQL tetap tersedia.

## Database dan bootstrap

Migrasi `0002_admin_monitoring` bersifat additive. Migrasi ini membuat schema `admin` dan `ingestion`, tabel sesi/token reset/rate-limit/audit/run/error, dan membuat `ingestion.documents` hanya jika belum ada. Jika tabel dokumen sudah ada, kolom monitoring yang belum tersedia ditambahkan tanpa `DROP` atau penghapusan baris. Nilai status lama tidak dikonversi secara spekulatif. Pada SQLite lokal schema terpisah dipetakan ke file pendamping; production gunakan PostgreSQL.

Setelah mengisi konfigurasi DB:

```powershell
alembic upgrade head
python -m scripts.bootstrap_admin admin@example.org
```

Jalankan bootstrap secara interaktif pada terminal privat. Password diminta melalui prompt tersembunyi, tidak diterima sebagai argumen shell. Perintah hanya membuat admin pertama; hash menggunakan scrypt, dan akun wajib mengganti password saat login pertama. Tidak ada endpoint pendaftaran.

Cookie sesi admin opaque, `HttpOnly`, `Secure` di production, `SameSite` sesuai konfigurasi, memiliki masa berlaku dan tersimpan sebagai digest di DB. Mutasi memerlukan CSRF header dan pemeriksaan origin. Rate limit login/reset tersimpan di PostgreSQL agar berlaku lintas worker. Reset memakai token acak sekali pakai; DB hanya menyimpan hash, link berlaku 30 menit, dan respons lupa password tidak mengungkap keberadaan akun. Reset menginvalidasi sesi yang ada. SMTP belum tersedia di repository, sehingga isi variabel SMTP dari provider organisasi sebelum mengaktifkan reset email.

## WF1 ingestion dan status Pinecone

Repository ini tidak memiliki export WF1 yang sebenarnya dan tidak menyediakan kredensial/index/source WF1. Karena itu, `workflows/wf1-success-callback.json` adalah **subworkflow helper**, bukan pengganti WF1. Impor helper tersebut, buat credential HTTP Header Auth `KPU Ingestion Callback Header` dengan header `X-Ingestion-Key`, lalu panggil helper dari workflow ingestion:

1. (Opsional tetapi disarankan) panggil pada awal eksekusi dengan `pinecone_confirmed=false`, `status=processing`.
2. Panggil lagi hanya pada jalur sukses setelah node Pinecone menerima upsert. Kirim `pinecone_confirmed=true`, `status=success`, `workflow=WF1`, `$execution.id`, `document_id`, `source_url`, metadata dokumen, `file_hash`, namespace WF1 yang sudah dikonfigurasi, serta jumlah chunk/Pasal yang benar-benar diketahui.
3. Jika jalur ingestion gagal dan masih berjalan, kirim `status=failed` dengan `pinecone_confirmed=false`. Jangan mengirim sukses hanya karena ekstraksi atau embedding selesai.
4. Jangan mengubah namespace/index atau chunking Pasal. Jika Pinecone menerima upsert tetapi callback gagal, jalankan ulang callback dengan idempotency yang sama; jangan menyimpulkan bahwa insert Pinecone gagal.

`scripts/ingest_pdfs.py` juga menulis keberhasilan ke PostgreSQL sesudah seluruh upsert Pinecone untuk dokumen tersebut kembali sukses. Log DB gagal akan menghentikan pencatatan state lokal sehingga proses dapat diulang dengan ID vektor deterministik.

Callback internal `POST /api/v1/admin/ingestion/callback` memerlukan `X-Ingestion-Key` yang sama dengan `INGESTION_CALLBACK_SECRET`. Jangan taruh secret di workflow export; simpan pada n8n credential dan `.env` server.

## WF2 error workflow

Impor `workflows/error-handler.json`; panduan node/credential berada di [`workflows/README.md`](./workflows/README.md). Di n8n, buka **WF1 → Settings → Error Workflow**, pilih `KPU WF2 - Error Handler`, lalu simpan WF1. Error workflow mencatat error secara idempotent di `ingestion.error_logs`, memperbarui status pencatatan WF2, dan mengirim notifikasi Telegram/email setelah credential dan penerima diisi.

n8n Error Trigger menerima kegagalan dari workflow yang dimulai trigger/scheduler, bukan eksekusi manual editor. Node dengan `Continue On Fail`, error output yang ditangani, atau jalur yang sudah menangani error mungkin tidak memanggil Error Workflow. Untuk kegagalan yang ditangani, hubungkan jalur error secara eksplisit ke pencatatan/notifikasi. Uji di staging; jangan memicu kegagalan buatan pada workflow produksi.

WF1 tidak tersedia di repository, jadi retry membutuhkan webhook khusus yang dibuat dan diuji di WF1. Set `ADMIN_RETRY_WEBHOOK_URL` ke webhook internal tersebut dan `ADMIN_RETRY_WEBHOOK_SECRET` setelah webhook menerapkan validasi `X-Admin-Retry-Secret`, `Idempotency-Key`, dan mengembalikan JSON `{"accepted": true, "execution_id": "..."}` hanya setelah eksekusi benar-benar diterima. Teruskan `error_id` sebagai `retry_error_id` ke callback helper WF1; status error asal baru menjadi `retry_succeeded` setelah callback sukses terkonfirmasi, atau `retry_failed` setelah workflow retry gagal. Rancang ulang pemrosesan agar idempotent terhadap file hash dan ID vektor yang sama. Jangan set URL contoh yang belum ada. API mengunci retry sebelum dispatch untuk mencegah duplikasi; timeout berarti status dispatch belum pasti dan perlu investigasi operator, bukan klik ulang. `accepted` berarti n8n menerima permintaan, **bukan** ingestion sukses.

## Konfigurasi

Salin template tanpa mengisi secret di Git:

- Lokal backend: `.env.example` → `.env`
- EC2 Compose: `infra/.env.example` → `infra/.env`
- Frontend lokal: `kpu-ai-agent-nextjs/.env.example` → `.env.local` (isi `FASTAPI_BASE_URL` dan `APP_ORIGIN`)

Production memerlukan PostgreSQL, nilai acak untuk `SESSION_SECRET`, `N8N_ENCRYPTION_KEY`, `ADMIN_RETRY_WEBHOOK_SECRET`, `INGESTION_CALLBACK_SECRET`, password DB acak yang URL-safe, `COOKIE_SECURE=true`, host DNS terpisah untuk aplikasi/n8n, SMTP, API key n8n untuk monitoring, serta credential Postgres/Telegram/SMTP/HTTP Header Auth yang dibuat di n8n. App memakai database dan role tersendiri (`APP_DB_*`); database/user PostgreSQL n8n yang sudah ada tidak diganti. Jangan kirim password/API key lewat chat atau commit `.env`.

## EC2 dengan Docker Compose

Jalankan dari folder `infra` setelah DNS `APP_HOST` dan `N8N_HOST` diarahkan ke EC2, port 80/443 dibuka, dan `.env` diisi secara privat:

```bash
cd /path/to/AI-Agent-KPU/infra
cp .env.example .env
# Edit .env secara lokal; jangan commit atau menyalin nilainya ke log.
docker compose build
docker compose up -d postgres
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01-create-app-db.sql'
docker compose run --rm kpu-backend alembic upgrade head
docker compose run --rm kpu-backend python -m scripts.bootstrap_admin admin@example.org
docker compose up -d
docker compose ps
docker compose logs --tail=100 kpu-backend kpu-frontend caddy
```

Migrasi dan bootstrap dilakukan sebelum service naik; keduanya tidak dijalankan otomatis oleh container. Perintah di atas tidak dijalankan oleh perubahan ini. PostgreSQL tetap pada volume Compose yang ada. Untuk rollout berikutnya, backup database/volume secara operasional terlebih dahulu, jalankan migrasi additive, lalu bangun dan naikkan service.

Init SQL menggunakan `CREATE ROLE/DATABASE` bersyarat dan aman dijalankan ulang. Untuk volume PostgreSQL yang sudah ada, perintah `psql` di atas membuat database/role app yang belum ada tanpa menyentuh database n8n; jika role sudah ada, pastikan password-nya sesuai `APP_DB_PASSWORD` secara privat. Jangan mengubah `POSTGRES_DB`, `POSTGRES_USER`, atau `POSTGRES_PASSWORD` pada volume aktif.

## Uji end-to-end

1. Jalankan `alembic upgrade head`, bootstrap admin di staging, buka `/admin/login`, lalu ganti password awal.
2. Pastikan tanpa cookie login, endpoint dashboard menjawab 401; role/session tidak valid ditolak; logout dan reset password menginvalidasi sesi.
3. Lakukan forgot-password untuk alamat terdaftar dan tidak terdaftar; respons publik harus sama. Pastikan email hanya sampai ke mailbox admin yang benar dan token tidak muncul pada log.
4. Jalankan workflow ingestion staging untuk satu dokumen resmi yang sudah disetujui. Periksa callback `processing`, hasil upsert Pinecone, callback `success`, lalu verifikasi metadata, `file_hash`, namespace, timestamp, dan jumlah aktual pada halaman Documents.
5. Uji status failed pada staging. Pastikan Error Trigger mencatat workflow/execution/node/pesan, detail ternormalisasi, notifikasi, dan tidak menandai Pinecone sukses.
6. Konfigurasikan webhook retry WF1 yang idempotent di staging. Klik Retry sekali; pastikan penerimaan n8n menghasilkan status menunggu konfirmasi, request duplikat ditolak, dan UI tidak menyatakan selesai sebelum callback sukses.
7. Pastikan halaman chat masyarakat, riwayat, dan draf e-PPID tetap berjalan seperti sebelumnya.

Automated tests: `python -m pytest -q`; frontend: `npm run lint`, `npx tsc --noEmit`, dan `npm run build`.
