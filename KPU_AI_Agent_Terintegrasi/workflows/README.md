# Workflow n8n KPU dan integrasinya dengan halaman admin

Folder ini berisi export dua workflow yang berjalan di n8n:

| File | Workflow | Hubungan ke halaman admin |
| --- | --- | --- |
| `WF1 - Ingestion PDF KPU per Pasal.json` | Ingestion PDF JDIH → Pinecone | Setelah Pinecone menerima upsert, node **Kirim Status Sukses ke Admin** memanggil `POST /api/v1/admin/ingestion/callback` → muncul di **Dashboard → Documents**. Webhook-nya juga menjadi target tombol **Retry** di **Dashboard → Errors**. |
| `WF2- Error Handler dan Monitoring KPU (execution log).json` | Error Trigger | Node **Kirim Error ke Admin** memanggil `POST /api/v1/admin/ingestion/error` → muncul di **Dashboard → Errors** dengan status `failed` (bisa di-Retry). |

Halaman **Dashboard → Workflows** membaca daftar workflow dan 100 eksekusi terbaru langsung dari n8n REST API (`N8N_API_URL` + `N8N_API_KEY`).

Export tidak berisi secret. Setelah impor, pilih credential pada node yang disebut di bawah.

## Alur data

```
Jadwal 06.00 ─► JDIH ─► cek ingestion.documents ─┐
Webhook (manual / Retry admin) ─► respon {accepted, execution_id} ─┤
                                                   ▼
          Siapkan Dokumen ─► Download PDF ─► Hitung Hash File ─┬► Kirim Status Processing ke Admin
                                                               └► Extract PDF ─► Pinecone (insert)
          ─► Rangkum Hasil Upsert ─► Kirim Status Sukses ke Admin  (status=success, pinecone_confirmed=true)

Error apa pun di WF1 ─► WF2 Error Trigger ─► Kirim Error ke Admin
```

Index (`kpu-subang-rag`), namespace (`kpu_kab_subang`), dan text splitter tidak diubah.

**Yang di-embed adalah teks asli hasil ekstraksi PDF**, bukan hasil tulis ulang AI. Node "Normalisasi ke Markdown / JSON" dihapus: menulis ulang seluruh peraturan dengan LLM berisiko memotong atau mengubah isi pasal, sehingga chatbot bisa mengutip teks yang tidak ada di dokumen aslinya.

Setiap chunk di Pinecone membawa metadata yang dibutuhkan chatbot untuk menampilkan sumber dan menerapkan guardrail: `source_url`, `document_id`, `title`, `document_type`, `document_number`, `year`, `legal_status`, `file_hash`. `title` dan `legal_status` dibaca dari halaman detail JDIH. Jika status tidak terbaca, nilainya `belum_diverifikasi` dan jawaban chatbot diberi catatan. Dokumen `tidak_berlaku` tidak pernah dipakai sebagai bukti.

Vektor lama yang dimasukkan sebelum perubahan ini tidak punya metadata tersebut, sehingga diabaikan chatbot. Sebaiknya kosongkan namespace `kpu_kab_subang` di konsol Pinecone, lalu jalankan **Pindai JDIH sekarang** dari halaman admin Dokumen.

## Langkah pemasangan

1. **Backend** — pastikan `.env` server (folder `infra`) berisi nilai acak privat untuk:
   - `INGESTION_CALLBACK_SECRET`
   - `ADMIN_RETRY_WEBHOOK_SECRET`
   - `ADMIN_RETRY_WEBHOOK_URL=http://n8n:5678/webhook/kpu-ingest-pdf`
   - `N8N_API_KEY` (buat di n8n: **Settings → n8n API**), `N8N_API_URL=http://n8n:5678`

   Lalu bangun ulang dan jalankan backend: `docker compose build kpu-backend && docker compose up -d kpu-backend`.
2. **Credential n8n** (buat di n8n, jangan di Git):
   - **KPU Ingestion Callback Header** — tipe *Header Auth*, name `X-Ingestion-Key`, value = `INGESTION_CALLBACK_SECRET`.
   - **KPU - Webhook Ingestion Auth** (sudah ada, dipakai node *Webhook Ingestion*) — ubah name header menjadi `X-Admin-Retry-Secret`, value = `ADMIN_RETRY_WEBHOOK_SECRET`.
   - **Postgres account** di node *periksa dokumen yang sudah diproses* harus mengarah ke **database aplikasi** (`APP_DB_*`, tempat tabel `ingestion.documents` dibuat oleh Alembic), bukan database internal n8n.
3. **Impor WF2** — buka WF2 di editor → menu `…` → *Import from File* → pilih file WF2. Pada node **Kirim Error ke Admin** pilih credential *KPU Ingestion Callback Header*. Simpan dan pastikan aktif.
4. **Impor WF1** dengan cara yang sama. Pilih credential *KPU Ingestion Callback Header* pada node **Kirim Status Sukses ke Admin**. Buka **Settings → Error Workflow** dan pastikan terpilih WF2 (export sudah berisi ID `mESA9ldYO9uzhHzA`; jika ID WF2 Anda berbeda, pilih ulang). Simpan dan aktifkan.

Impor ke workflow yang sudah ada (bukan membuat workflow baru) supaya ID workflow dan URL webhook tetap sama.

## Kontrol dari halaman admin

Halaman **Dashboard → Dokumen** punya panel **Kontrol ingestion**:

- **Pindai JDIH sekarang**: menjalankan WF1 seperti jadwal harian (dokumen yang sudah `success` dilewati).
- **Ingest PDF ini**: memproses satu URL PDF resmi (host harus ada di `RAG_ALLOWED_HOSTS`, mis. `jdih.kpu.go.id`).

Tabel dokumen otomatis diperbarui setiap 15 detik selama ada dokumen `processing`. Jika WF2 mencatat error, banner merah muncul di semua halaman admin dan menu Error log menampilkan jumlahnya.

Backend memerlukan `PINECONE_NAMESPACE=kpu_kab_subang` (default baru) dan `PINECONE_INDEX_NAME=kpu-subang-rag` agar chatbot membaca vektor dari WF1.

## Memanggil WF1 lewat webhook

```bash
curl -X POST https://<N8N_HOST>/webhook/kpu-ingest-pdf \
  -H "X-Admin-Retry-Secret: <ADMIN_RETRY_WEBHOOK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"pdf_url": "https://jdih.kpu.go.id/data/data_pkpu/....pdf", "title": "PKPU ..."}'
```

- Dengan `pdf_url`: hanya PDF itu yang diproses (tanpa cek duplikat).
- Tanpa `pdf_url` (dipakai tombol **Retry** admin, body berisi `error_id`): menjalankan pemindaian JDIH yang sama seperti jadwal harian; dokumen yang sudah `success` dilewati. Setiap dokumen yang berhasil dikirim dengan `retry_error_id`, sehingga error asal berubah menjadi `retry_succeeded`. Jika eksekusi retry gagal, WF2 menandai error asal `retry_failed`.
- Webhook segera membalas `{"accepted": true, "execution_id": "..."}`; itu berarti eksekusi diterima, **bukan** ingestion selesai.

## Batasan yang perlu diketahui

- Error Trigger n8n tidak berjalan untuk eksekusi manual dari editor. Uji dengan jadwal atau webhook.
- Jika Retry tidak menemukan dokumen baru (semua sudah `success`), tidak ada callback, sehingga status error tetap `retry_requested`.
- `pasal_count` dihitung dari jumlah nomor `Pasal N` unik pada chunk yang di-upsert.
- Node HTTP memanggil `http://kpu-backend:8000` (jaringan internal Docker Compose di `infra/compose.yaml`). Jika n8n tidak berada di compose yang sama, ganti URL pada node **Kirim Status Sukses ke Admin** dan **Kirim Error ke Admin** dengan URL backend yang dapat dijangkau n8n.
