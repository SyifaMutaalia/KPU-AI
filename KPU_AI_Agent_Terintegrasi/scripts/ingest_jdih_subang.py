"""Ingest Keputusan KPU Kabupaten Subang dari JDIH KPU ke Pinecone, dengan OCR.

Sumber: JDIH KPU > Koleksi Kab/Kota > Jawa Barat > Kabupaten Subang
(https://jdih.kpu.go.id/koleksi/kabkot/32/3213). Sebagian besar PDF keputusan
daerah adalah hasil scan tanpa teks, sehingga halaman tanpa teks dibaca dengan
OCR berbasis LLM (model vision OpenAI) yang diminta menyalin teks apa adanya.

Alurnya sama dengan scripts/ingest_jdih_awal.py: metadata dari halaman detail
(judul, nomor, tahun, status) -> unduh PDF -> teks (atau OCR) -> potong 1.000
karakter -> embedding OpenAI -> upsert Pinecone -> lapor ke dashboard admin.
Secara default hanya dokumen berstatus "Berlaku" tahun 2024-2026 yang diproses. Dokumen yang sudah sukses (file_hash
sama) dilewati, sehingga script aman dijalankan ulang.

Contoh:
  python -m scripts.ingest_jdih_subang --backend https://ai-agent-kpu-api.vercel.app

Butuh: pymupdf, serta variabel OPENAI_API_KEY (opsional OPENAI_OCR_MODEL), PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_NAMESPACE,
INGESTION_CALLBACK_SECRET.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import uuid
from html import unescape
from pathlib import Path

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from pinecone import Pinecone
from pypdf import PdfReader

JDIH = "https://jdih.kpu.go.id"
COLLECTION = f"{JDIH}/koleksi/to_kabkot/32/3213/kepkpukabkot"
LISTING = f"{JDIH}/kepkpukabkot"
PDF_PREFIX = f"{JDIH}/data-kabko/subang/"
DETAIL_RE = re.compile(r'href="(https://jdih\.kpu\.go\.id/kepkpukabkot/detail/[^"]+)"')
PDF_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+\.pdf)["\']', re.I)
TITLE_RE = re.compile(r"(Keputusan Komisi Pemilihan Umum Kabupaten Subang Nomor .+?)\s+Tipe\s*:", re.I)
STATUS_RE = re.compile(r"Keterangan Status\s*:\s*(Tidak Berlaku|Dicabut|Berlaku|Diubah)", re.I)
OCR_PROMPT = (
    "Ini satu halaman hasil scan dokumen resmi KPU Kabupaten Subang. Salin SELURUH teks pada halaman "
    "persis seperti tertulis, dalam bahasa aslinya, urut dari atas ke bawah. Pertahankan nomor, tanggal, "
    "nama, angka, dan penomoran pasal/diktum. Tabel ditulis baris per baris dengan pemisah ' | '. "
    "Jangan meringkas, menerjemahkan, menambah, atau menebak; tulis [tidak terbaca] untuk bagian yang tidak "
    "terbaca. Abaikan tanda tangan, stempel, dan gambar. Keluarkan hanya teks halaman."
)
WORKFLOW = "Ingest JDIH KPU Subang"
DOCUMENT_TYPE = "Keputusan KPU Kabupaten Subang"


def plain(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    """GET dengan jeda dan pengulangan: server JDIH kadang lambat atau memutus koneksi."""
    for attempt in range(4):
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            time.sleep(0.7)
            return response
        except httpx.HTTPError:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def legal_status(value: str | None) -> str:
    value = (value or "").lower()
    if value == "berlaku":
        return "berlaku"
    if value in {"tidak berlaku", "dicabut"}:
        return "tidak_berlaku"
    return "belum_diverifikasi"


def list_documents(client: httpx.Client, limit: int) -> list[dict]:
    get(client, COLLECTION)  # menetapkan wilayah Kabupaten Subang di sesi
    details: list[str] = []
    for page in range(1, 40):
        html = get(client, LISTING, params={"page_kepkpukabkot": page}).text
        found = [u for u in dict.fromkeys(DETAIL_RE.findall(html)) if u not in details]
        if not found:
            break
        details += found
    docs = []
    for url in dict.fromkeys(details):
        html = get(client, url).text
        pdfs = [p for p in PDF_RE.findall(html) if p.startswith(PDF_PREFIX) and "/data_kepkpud/" in p]
        if not pdfs:
            continue  # bukan milik KPU Kabupaten Subang
        text = plain(html)
        title = TITLE_RE.search(text)
        status = STATUS_RE.search(text)
        number = year = None
        if title:
            found = re.search(r"Nomor\s+([\w./-]+?)\s+Tahun\s+(\d{4})", title.group(1), re.I)
            if found:
                number, year = found.group(1), int(found.group(2))
        docs.append({
            "pdf_url": pdfs[0], "detail_url": url,
            "title": title.group(1).strip()[:500] if title else None,
            "legal_status": legal_status(status.group(1) if status else None),
            "document_number": number, "year": year,
        })
        if len(docs) >= limit:
            break
    return docs


def ocr_page(openai: OpenAI, model: str, png: bytes) -> str:
    image = "data:image/png;base64," + base64.b64encode(png).decode()
    for attempt in range(3):
        try:
            response = openai.responses.create(
                model=model, store=False, reasoning={"effort": "low"}, max_output_tokens=6000,
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": OCR_PROMPT},
                    {"type": "input_image", "image_url": image, "detail": "high"},
                ]}],
            )
            return (response.output_text or "").strip()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    return ""


def pdf_text(content: bytes, openai: OpenAI, model: str) -> tuple[str, int]:
    """Teks PDF; halaman tanpa teks dibaca dengan OCR LLM. Mengembalikan (teks, jumlah halaman OCR)."""
    import fitz  # pymupdf

    reader = PdfReader(io.BytesIO(content))
    document = fitz.open(stream=content, filetype="pdf")
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    scanned = [i for i, text in enumerate(pages) if len(text) < 80]
    images = {i: document[i].get_pixmap(dpi=150).tobytes("png") for i in scanned}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, text in zip(scanned, pool.map(lambda i: ocr_page(openai, model, images[i]), scanned)):
            pages[i] = text
    return "\n".join(pages).strip(), len(scanned)


def callback(client: httpx.Client, backend: str, secret: str, payload: dict) -> None:
    response = client.post(
        backend.rstrip("/") + "/api/v1/admin/ingestion/callback",
        json=payload, headers={"X-Ingestion-Key": secret}, timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"callback HTTP {response.status_code}: {response.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", required=True, help="URL backend FastAPI")
    parser.add_argument("--limit", type=int, default=500, help="maksimum dokumen diproses")
    parser.add_argument("--list-file", help="simpan/baca daftar dokumen (JSON) agar crawl tidak diulang")
    parser.add_argument("--year-from", type=int, default=2024)
    parser.add_argument("--year-to", type=int, default=2026)
    parser.add_argument("--include-unverified", action="store_true",
                        help="ikut proses dokumen berstatus Diubah/tanpa status (default: hanya Berlaku)")
    parser.add_argument("--skip-hashes", help="file berisi file_hash dokumen yang sudah sukses, satu per baris")
    args = parser.parse_args()

    namespace = os.environ["PINECONE_NAMESPACE"]
    secret = os.environ["INGESTION_CALLBACK_SECRET"]
    openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=180)
    ocr_model = os.environ.get("OPENAI_OCR_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-6-luna")
    pinecone_options = {}
    if os.environ.get("HTTPS_PROXY"):  # SDK Pinecone tidak membaca proxy dari environment
        pinecone_options["proxy_url"] = os.environ["HTTPS_PROXY"]
        if os.environ.get("SSL_CERT_FILE"):
            pinecone_options["ssl_ca_certs"] = os.environ["SSL_CERT_FILE"]
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"], **pinecone_options).Index(
        os.environ["PINECONE_INDEX_NAME"]
    )
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    skip = set()
    if args.skip_hashes and Path(args.skip_hashes).exists():
        skip = {line.strip() for line in Path(args.skip_hashes).read_text().splitlines() if line.strip()}
    execution_id = f"subang-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    headers = {"User-Agent": "Mozilla/5.0 (compatible; KPU-AI-Agent-Ingestion/1.0)"}
    with httpx.Client(timeout=120, follow_redirects=True, headers=headers) as client:
        if args.list_file and Path(args.list_file).exists():
            documents = json.loads(Path(args.list_file).read_text())
        else:
            documents = list_documents(client, args.limit)
            if args.list_file:
                Path(args.list_file).write_text(json.dumps(documents, ensure_ascii=False, indent=1))
        allowed = {"berlaku", "belum_diverifikasi"} if args.include_unverified else {"berlaku"}
        documents = list({d["pdf_url"]: d for d in documents}.values())
        documents = [
            d for d in documents
            if d["legal_status"] in allowed and d["year"] and args.year_from <= d["year"] <= args.year_to
        ][: args.limit]
        print(f"{len(documents)} Keputusan KPU Kabupaten Subang akan diproses; execution {execution_id}")

        ok = failed = skipped = 0
        for n, doc in enumerate(documents, 1):
            document_id = "jdih-" + hashlib.sha256(doc["pdf_url"].encode()).hexdigest()
            label = (doc["title"] or doc["pdf_url"])[:90]
            base = {
                "workflow": WORKFLOW, "execution_id": f"{execution_id}-{n}",
                "document_id": document_id, "source_url": doc["pdf_url"],
                "document_type": DOCUMENT_TYPE, "document_number": doc["document_number"],
                "title": doc["title"], "year": doc["year"], "namespace": namespace,
            }
            try:
                content = get(client, doc["pdf_url"]).content
                file_hash = hashlib.sha256(content).hexdigest()
                if file_hash in skip:
                    skipped += 1
                    continue
                callback(client, args.backend, secret, {**base, "status": "processing", "file_hash": file_hash})
                text, ocr_pages = pdf_text(content, openai, ocr_model)
                if len(text) < 200:
                    raise RuntimeError("teks tidak terbaca bahkan setelah OCR")
                text = re.sub(r"\[tidak terbaca\]", "", text)
                chunks = [c for c in splitter.split_text(text) if c.strip()]
                metadata = {
                    "source_url": doc["pdf_url"], "document_id": document_id,
                    "title": doc["title"] or "", "document_type": DOCUMENT_TYPE,
                    "document_number": doc["document_number"] or "", "year": doc["year"] or "",
                    "legal_status": doc["legal_status"], "file_hash": file_hash,
                    "text_source": "ocr_llm" if ocr_pages else "pdf_text",
                }
                for start in range(0, len(chunks), 100):
                    batch = chunks[start:start + 100]
                    vectors = openai.embeddings.create(
                        model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"), input=batch,
                    ).data
                    index.upsert(namespace=namespace, vectors=[
                        {"id": f"{document_id}-{start + i}", "values": v.embedding,
                         "metadata": {**metadata, "text": chunk, "chunk_index": start + i}}
                        for i, (chunk, v) in enumerate(zip(batch, vectors))
                    ])
                pasal = {m.group(1) for m in re.finditer(r"\bPasal\s+(\d+[A-Z]?)\b", text)}
                callback(client, args.backend, secret, {
                    **base, "status": "success", "file_hash": file_hash,
                    "chunks_count": len(chunks), "pasal_count": len(pasal) or None,
                    "pinecone_confirmed": True,
                })
                ok += 1
                print(f"[{n}/{len(documents)}] OK {len(chunks)} chunk (OCR {ocr_pages} hal): {label}", flush=True)
            except Exception as exc:
                failed += 1
                print(f"[{n}/{len(documents)}] GAGAL {type(exc).__name__}: {exc} :: {label}", flush=True)
                try:
                    callback(client, args.backend, secret, {**base, "status": "failed"})
                except Exception as cb_exc:
                    print("   callback failed juga gagal:", cb_exc)
        print(f"Selesai: {ok} sukses, {failed} gagal, {skipped} dilewati (sudah ada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
