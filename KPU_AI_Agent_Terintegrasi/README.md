> **PETUNJUK TERBARU:** Baca [`CARA_MENJALANKAN.md`](./CARA_MENJALANKAN.md) lebih dahulu. Folder `kpu-ai-agent-nextjs/` sudah diintegrasikan melalui Next.js API proxy. File `.env.example` adalah placeholder yang aman; gunakan kredensial baru setelah rotasi.

# Backend AI Agent Pelayanan Informasi Kepemiluan — KPU Kabupaten Subang

**Status:** fondasi MVP dan starter implementasi skripsi, **belum audit produksi/penetration test**. Backend ini memisahkan REST API, agent LangChain v1 (graf LangGraph), retrieval Pinecone, database riwayat, draf permohonan e-PPID, serta validasi keamanan. Tidak mengubah data pemilih, tidak mengajukan e-PPID otomatis, dan tidak memerlukan akun publik.

## 1. Arsitektur

```text
Next.js (browser)
   |  HTTPS + Cookie HttpOnly + X-CSRF-Token
   v
FastAPI (app/main.py)
   |-- /api/v1/session                    -> session anonim / CSRF token
   |-- /api/v1/chat                       -> LangChain create_agent (LangGraph)
   |      |-- search_kpu_documents        -> embedding -> Pinecone -> metadata sumber
   |      |-- prepare_eppid_draft         -> teks draf 2 isian (tanpa submit)
   |      +-- official_channels           -> link resmi, bukan KB
   |-- /api/v1/conversations             -> SQLAlchemy, dibatasi pemilik sesi
   |-- /api/v1/eppid/draft                -> LLM structured output (copy-ready)
   |-- /api/v1/admin/*                   -> autentikasi admin dan monitoring ingestion
   +-- /health                           -> liveness saja

n8n/Docker -> WF1 ingestion (tetap dikelola operator) -> Pinecone
           -> WF2 error log/notifikasi dan callback monitoring -> PostgreSQL
```

**Penting:** e-PPID digunakan sebagai **kanal permohonan informasi**, **bukan sumber RAG**. Dokumen sumber RAG hanya berasal dari domain resmi yang masuk allowlist `.env`. Metadata sumber diperiksa sebelum dipakai sebagai rujukan, dan retrieval memakai ambang kemiripan `RAG_MIN_SCORE` yang harus dituning lewat data pengujian. Ini bukan jaminan bahwa semua dokumen masih berlaku: status regulasi harus diverifikasi saat kurasi.

Admin login, migrasi monitoring, bootstrap akun pertama, integrasi workflow, konfigurasi EC2, dan batasan retry dijelaskan di [`ADMIN_MONITORING.md`](./ADMIN_MONITORING.md). Export WF1 (ingestion) dan WF2 (error handler) ada di [`workflows/`](./workflows/) beserta panduan impornya.

## 2. Persyaratan

- Python **3.12** (direkomendasikan; Dockerfile memakai Python 3.12)
- OpenAI API key untuk model dan embedding (ditanggung operator, tidak diberikan ke browser)
- Pinecone API key dan **index yang sudah dibuat** (index dense, dimensi **1536** untuk `text-embedding-3-small`, metrik cosine)
- PostgreSQL untuk penggunaan multi-instance di production. SQLite dipakai saat development lokal.
- n8n **opsional** untuk alur ingestion dan Error Workflow; monitoring UI tetap berjalan dengan data PostgreSQL yang tersedia.

### Menjalankan di Windows PowerShell (tanpa Docker)

Buka terminal di folder `backend`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Salin hasil token acak tersebut ke `SESSION_SECRET` dalam `.env`. Jangan kirim secret ke chat, dan jangan pernah commit `.env` ke Git. Isi `OPENAI_API_KEY`, `PINECONE_API_KEY`, dan `PINECONE_INDEX_NAME` milik project-mu. `RAG_ENABLED` aktif secara default dan retrieval memakai `PINECONE_NAMESPACE` yang sudah dikonfigurasi; set `RAG_ENABLED=false` hanya jika retrieval memang ingin dinonaktifkan. Tentukan indeks Pinecone dengan dimensi yang sesuai model embedding.

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Coba `http://127.0.0.1:8000/health` dan `http://127.0.0.1:8000/docs` (Swagger hanya aktif di development). Health check tidak membuktikan provider AI siap; jika API key/indeks belum tersedia, `/health` dapat tetap mengembalikan `ok` tetapi `/chat` akan gagal dengan pesan 503 yang aman.

**Alternatif Docker lokal:**

```powershell
Copy-Item .env.example .env
# Edit .env, gunakan SESSION_SECRET acak
# Penting: database volume Docker; migrasi pertama harus dijalankan!
docker compose build
docker compose run --rm kpu-backend alembic upgrade head
docker compose up -d
```

Jalankan `docker compose logs kpu-backend` untuk melihat status teknis. Pastikan `.env` tidak dimasukkan image.

## 3. Endpoint API

| Method | Path | Keterangan |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/api/v1/session` | Membuat/memakai session anonim; response JSON berisi `csrf_token` |
| POST | `/api/v1/chat` | `{ "message": "...", "conversation_id": null }` |
| GET | `/api/v1/conversations` | Daftar percakapan pemilik cookie (maks. 100) |
| GET | `/api/v1/conversations/{uuid}` | Pesan dan sumber percakapan sendiri |
| DELETE | `/api/v1/conversations/{uuid}` | Hapus percakapan sendiri |
| POST | `/api/v1/eppid/draft` | `{ "information_needed": "...", "purpose": "..." }` |

Frontend Next.js menggunakan proxy same-origin (`kpu-ai-agent-nextjs/lib/backend.ts`) untuk meneruskan cookie `HttpOnly` dan header CSRF ke FastAPI. Browser berkomunikasi dengan `/api/session`, `/api/chat`, `/api/conversations`, dan `/api/eppid/draft` di domain Next.js. Lihat `CARA_MENJALANKAN.md` untuk panduan terbaru.

Sample hasil `POST /api/v1/chat`:

```json
{
  "conversation_id": "f39838ed-85f0-4c55-b2e5-6cc2c17dbdf0",
  "answer": "... [1]",
  "sources": [{"title": "Judul dokumen", "url": "https://jdih.kpu.go.id/..."}],
  "grounded": true
}
```

`grounded=true` **hanya berarti ada kutipan sumber tool yang valid**, bukan hasil verifikasi faktual otomatis atau sertifikat kebenaran jawaban. Evaluasi manusia dan dataset pengujian retrieval tetap perlu.

## 4. Pengisian knowledge base (RAG)

1. Identifikasi dokumen resmi relevan yang **masih berlaku** (website KPU Kabupaten Subang / JDIH KPU). Verifikasi metadata serta tanggal berlaku.
2. Ekstrak isi PDF/dokumen ke teks di luar API publik. Pastikan hasil ekstraksi benar, bahasa dan pasal tidak terpotong; **jangan** masukkan e-PPID sebagai sumber dokumen.
3. Siapkan JSON lokal terkurasi (`title`, `source_url`, `text`), lihat `examples/approved_documents.example.json` yang **hanya contoh, bukan fakta resmi**.
4. Validasi tanpa unggah:

   ```powershell
   python -m scripts.ingest_json .\examples\approved_documents.example.json --dry-run
   ```

5. Setelah mengganti contoh dengan **dokumen sungguhan dan memverifikasi semua URL dan konten**:

   ```powershell
   python -m scripts.ingest_json .\path\to\reviewed_documents.json --confirm-replace
   ```

**Peringatan:** `--confirm-replace` menghapus vektor lama untuk dokumen tersebut sebelum upsert vektor baru. Penggantian **tidak atomik**: jika proses gagal, ulangi ingestion. Jangan lakukan saat pengguna bergantung pada dokumen kritis; pertimbangkan namespace versi + cutover yang diverifikasi. Simpan backup daftar dokumen dan metadata; skrip tidak mendeteksi pencabutan regulasi atau duplikat lintas-URL. Belum tersedia crawling JDIH atau monitoring otomatis. Workflow n8n bisa menjalankan proses *staging* setelah proses validasi/approval, jangan beri n8n akses pemutakhiran basis pengetahuan tanpa kontrol.

## 5. Draf e-PPID

`POST /api/v1/eppid/draft` menghasilkan teks **informasi yang dimohon** serta **tujuan penggunaan informasi**. Bila tujuan tidak diberikan, field tujuan **dikosongkan**; jangan mengarang tujuan pemohon. Output bisa disalin ke situs resmi `https://subangkabppid.kpu.go.id/` setelah pengguna memeriksa isi dan kolom yang tersedia. Referensi tautan e-PPID tersebut berasal dari laman KPU Kabupaten Subang, tetapi **kolom formulir spesifik Subang belum diverifikasi langsung** saat starter ini disusun. Lengkapi/mapping ulang jika tampilan formulir berubah. Data KTP, alamat, telepon, atau kontak sensitif hanya diisi pada kanal resmi, **bukan pada AI Agent**. Fitur ini sama sekali tidak submit ke e-PPID.

## 6. Keamanan: yang sudah ada dan yang belum

Sudah ada:
- Secret disimpan di sisi server dalam `.env`, diabaikan Git/Docker build.
- Cookie sesi anonim acak (`HttpOnly`); server menyimpan **HMAC digest**, bukan cookie mentah.
- Cek kepemilikan sesi di semua endpoint riwayat. URL/UUID orang lain menghasilkan `404`.
- `X-CSRF-Token`, validasi `Origin`, konfigurasi CORS eksplisit, `no-store` dan security headers dasar.
- Limit per sesi per menit di database; validasi ukuran input; regex untuk menolak email, NIK, nomor telepon umum.
- Allowlist sumber HTTPS exact hostname (mencegah sebagian penyamaran tautan); tidak tersedia tool fetch arbitrary URL.
- Tidak ada endpoint publik untuk write ke Pinecone, submit e-PPID, mengubah data pemilih, atau menjalankan kode.
- Endpoint prod Swagger/OpenAPI dimatikan; error provider tidak memaparkan traceback/secret ke klien.

**Belum cukup untuk klaim bebas vulnerability:**
- Regex PII bukan DLP sempurna; konten pengguna tetap dikirim ke provider LLM ketika mengaktifkan chat/draf. Evaluasi perlindungan data, kebijakan penyimpanan, persetujuan, dan kebutuhan institusi.
- Riwayat chat tergantung cookie perangkat/browser. Kehilangan cookie berarti riwayat tidak dapat dipulihkan tanpa autentikasi. Pengguna komputer bersama harus dapat menghapus riwayat; penghapusan otomatis sesi perlu dijadwalkan.
- Database SQLite hanya pengembangan. PostgreSQL, migrasi Alembic, TLS, secret manager, cookie `Secure=true`, backup, monitoring dan proteksi edge berbasis IP wajib dipertimbangkan untuk deployment.
- Rate limit berbasis sesi dapat dilewati dengan cookie baru; lindungi pada lapisan proxy/WAF dan batasi penggunaan API LLM untuk mencegah biaya tak terkendali.
- Tidak ada audit penetrasi, moderasi menyeluruh, sanitasi malware pada ingestion, atau verifikasi kebenaran berbasis LLM-as-judge. Diperlukan pengujian red-team untuk prompt injection dan dokumen salah/masa berlaku habis.
- Tidak ada audio/STT, login/registrasi, scheduled tasks, atau antarmuka Next.js utuh dalam paket **backend** ini.
- Developer Tools browser (`F12`) **tidak dapat dinonaktifkan secara aman**. Kode JavaScript yang dikirim ke browser bisa dilihat; rahasia harus tetap di backend.

Untuk cleanup berkala, jadwalkan `python -m scripts.cleanup` melalui scheduler internal (contoh: sekali per hari). Penghapusan sesi kedaluwarsa menghapus riwayat berdasarkan `ON DELETE CASCADE`, jika foreign-key enforcement database aktif.

## 7. Pengujian

```powershell
pytest -q
python -m compileall -q app scripts alembic
```

Test suite melakukan mock respons AI dan mencakup session+CSRF, kebocoran akses riwayat, data pribadi, URL allowlist, dan penghapusan chat. **Tidak ada uji koneksi nyata OpenAI/Pinecone dalam test suite ini.** Tambahkan pengujian end-to-end setelah menyiapkan credentials aman dan dataset dokumen yang sudah diverifikasi. Uji waktu pencarian, jumlah langkah, relevansi retrieval, abstention, kesesuaian jawaban beserta sumbernya untuk evaluasi Bab IV.

## 8. Deployment yang disarankan

- Frontend Next.js di Vercel; backend FastAPI di layanan yang mendukung proses Python/API + PostgreSQL terkelola (atau VPS/Docker).
- Jalankan backend via HTTPS, gunakan domain aplikasi **same-site** atau BFF/proxy Next.js untuk menghindari masalah third-party cookie. Jika beda site, rancang ulang strategi cookie, CORS dan CSRF; jangan asal ganti `SameSite=None`.
- Deploy PostgreSQL dan jalankan `alembic upgrade head` **sebelum** menaikkan versi API.
- n8n menjalankan workflow monitor/kurasi dokumen dalam Docker terpisah dan hanya meneruskan dokumen resmi yang disetujui untuk ingestion.
- Gunakan model dan API keys institusional berizin, jangan API key pinjaman di produksi tanpa izin dan kontrol biaya.

## 9. Rujukan teknis saat pembuatan

- LangChain v1 Agent API `create_agent`: https://reference.langchain.com/python/langchain/agents/factory/create_agent
- PineconeVectorStore: https://reference.langchain.com/python/langchain-pinecone/vectorstores/PineconeVectorStore
- KPU Kabupaten Subang tentang e-PPID: https://kab-subang.kpu.go.id/index.php/blog/category/104?page=6

> **Catatan kejujuran status:** pengujian mock lokal dapat berjalan tanpa kredensial, tetapi instalasi paket LangChain/Pinecone dan pengujian panggilan eksternal belum dilakukan pada lingkungan pembuat paket karena akses `pip` ke internet tidak tersedia. Versi dependensi dipilih berdasarkan referensi API resmi, namun tetap harus diuji langsung setelah instalasi pada komputer pengguna.

---

## 10. Fase awal: ingestion PDF 205 Keputusan KPU Subang + 380 PKPU melalui LangChain (tanpa n8n)

Jumlah **205 + 380 = 585 dokumen** adalah target inventaris dari pengguna, **belum** hasil verifikasi tanggal/status hukum. Tidak semua dari 585 dokumen otomatis dapat menjadi rujukan AI Agent. Dokumen berstatus `dicabut`, `diubah`, atau `belum_diverifikasi` tetap tercatat di manifest, tetapi tidak diindeks untuk jawaban publik sampai status dan versi konsolidasinya diperiksa. Script ini tidak melakukan crawling dan tidak memutuskan status hukum secara otomatis.

**Sumber PDF asli** berada di folder lokal `backend/data/kpu_documents/`, bukan disimpan di Pinecone. Pinecone menampung teks per potongan, vektor embedding, dan metadata. Folder `data/` tidak di-commit ke Git; buat cadangan privat PDF dan `data/ingestion_state.json` secara teratur.

Struktur yang direkomendasikan:

```text
backend/
  data/                              # diabaikan Git dan Docker build
    kpu_manifest.csv                 # inventaris hasil kurasi (585 baris jika semuanya tersedia)
    ingestion_state.json             # dibuat oleh skrip sesudah upload; WAJIB dibackup
    kpu_documents/
      keputusan_kpu_subang/
        ... .pdf
      pkpu/
        ... .pdf
  app/rag/pdf_catalog.py             # metadata, validasi URL/path/status hukum
  app/rag/pdf_chunks.py              # pypdf + LangChain text splitter
  scripts/ingest_pdfs.py             # CLI preview dan upload bertahap
  scripts/create_manifest.py         # pembuat draft CSV berdasarkan nama PDF
  examples/kpu_manifest.template.csv # header template, BUKAN data faktual
```

Siapkan `.csv` sesuai header template dengan kolom:

| Kolom | Contoh format / aturan |
|---|---|
| `file_path` | `pkpu/nama_file.pdf` (relatif ke `data/kpu_documents`) |
| `document_type` | `pkpu` atau `keputusan_kpu_subang` |
| `document_number` | nomor keputusan/peraturan sesuai dokumen |
| `year` | tahun resmi terbit, misalnya `2024` |
| `title` | judul sesuai dokumen resmi |
| `source_url` | URL HTTPS resmi, bukan URL random dan bukan e-PPID |
| `legal_status` | `berlaku`, `diubah`, `dicabut`, atau `belum_diverifikasi` |
| `issued_date` | tanggal `YYYY-MM-DD`, boleh kosong jika belum diverifikasi |

> Jangan menggunakan metadata dummy dari contoh untuk memasukkan data riil. `source_url` sebaiknya menunjuk ke detail dokumen/PDF spesifik agar rujukan yang diberikan kepada masyarakat dapat diperiksa, bukan hanya homepage. Pastikan domain URL telah dicantumkan dalam `RAG_ALLOWED_HOSTS` **setelah** memastikan domain resmi.

### Tahap A — validasi inventaris

```powershell
# Buat folder, simpan PDF dan isi manifest CSV terlebih dahulu
New-Item -ItemType Directory -Force data/kpu_documents/keputusan_kpu_subang, data/kpu_documents/pkpu
# Setelah 585 file PDF benar-benar tersedia di masing-masing subfolder,
# buat draft inventaris (kolom penting sengaja kosong):
python -m scripts.create_manifest

# Edit data/kpu_manifest.csv: lengkapi semua nomor/tahun/judul/URL/status resmi.
# Setelah seluruh baris diperiksa:
python -m scripts.ingest_pdfs --check-manifest --expect-keputusan 205 --expect-pkpu 380
```

`--check-manifest` memvalidasi file, kategori, nomor, tahun, judul, URL, dan status tanpa membuka seluruh PDF dan tanpa memerlukan panggilan LLM/embedding. Pemeriksaan keberlakuan tetap dilakukan manusia dengan membandingkan status pada JDIH.

### Tahap B — uji chunking lokal LangChain

```powershell
# Hanya 5 dokumen berlaku pertama, tanpa biaya embedding dan tidak menulis Pinecone
python -m scripts.ingest_pdfs --dry-run --limit 5

# Semua dokumen yang statusnya "berlaku", tanpa biaya embedding dan tidak menulis Pinecone
python -m scripts.ingest_pdfs --dry-run --expect-keputusan 205 --expect-pkpu 380
```

LangChain `RecursiveCharacterTextSplitter` menggunakan parameter awal `chunk_size=1000`, `chunk_overlap=150` **dalam karakter**, bukan token. Setiap chunk dibangun dari **satu halaman** agar sumber `page` jelas; potongan bisa terbelah di tengah pasal lintas halaman, sehingga relevansi dan jawaban hukum perlu dievaluasi. Proses menggunakan `pypdf` untuk membaca text layer. PDF scan/gambar tanpa teks **tidak otomatis menjadi dapat dibaca**: dokumen semacam itu harus melalui OCR dan verifikasi manusia sebelum diindeks. Laporan halaman minim teks adalah tanda peringatan untuk QA; **bukan** bukti PDF sudah diekstrak sempurna.

### Tahap C — uji unggah ke Pinecone (5 dokumen dulu)

1. Buat index Pinecone untuk `text-embedding-3-small`, dimensi 1536 dan metrik cosine (jika model berbeda, cek dimensinya).
2. Isi `OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` di `.env`; jangan bagikan key. Agar tidak tercampur data uji lama, gunakan namespace baru misalnya `PINECONE_NAMESPACE=kpu-subang-pdf-v1`.
3. Gunakan perintah:

```powershell
python -m scripts.ingest_pdfs --confirm-upload --limit 5
```

Jika QA retrieval 5 dokumen sudah benar, lakukan unggah kategori penuh:

```powershell
python -m scripts.ingest_pdfs --confirm-upload --expect-keputusan 205 --expect-pkpu 380
```

Proses mengunggah maksimal **50 chunks per batch**, tetapi **embedding API tetap memerlukan biaya sesuai jumlah teks**. PDF diproses satu per satu untuk membatasi konsumsi memori. Versi dokumen dan metadata di-*fingerprint*; versi baru diunggah dulu, lalu ID versi lama dari state lokal dihapus. Jika status pada manifest berubah menjadi selain `berlaku`, vektor sebelumnya dibersihkan saat **unggah penuh** (`--limit` tidak melakukan pembersihan ini). Dokumen yang **hilang dari CSV** tidak otomatis dihapus dari indeks; lakukan rekonsiliasi inventaris dan state secara terencana. Proses ini belum atomik dan belum aman untuk dieksekusi paralel.

**Penting:** status `berlaku` di CSV adalah klaim kurator, bukan verifikasi hukum otomatis. Untuk regulasi yang diubah, periksa teks terkonsolidasi dan hubungan perubahan sebelum memperbolehkan jawaban. Pada jalur retrieval, kueri disaring oleh metadata `legal_status=berlaku`, sehingga dataset lama tanpa metadata status tidak ditampilkan. Perlu evaluasi relevansi jawaban dan rujukan dari dokumen lengkap sebelum publikasi.

### Tahap D — n8n setelah ingestion manual tervalidasi

n8n kelak bertugas mendeteksi dokumen baru/perubahan dari JDIH, mencatat perubahan dan meminta kurasi/approval. **n8n tidak perlu menduplikasi logika PDF extraction, splitter, embedding, dan Pinecone**; cukup memicu skrip/job ingestion yang sama melalui jalur internal yang diautentikasi, setelah PDF+metadata lolos verifikasi. Tidak ada endpoint ingestion publik dalam backend ini.
