"""Ingest awal Peraturan KPU dari JDIH KPU ke Pinecone (setara dengan WF1 n8n).

Dipakai untuk mengisi index sekali di awal; setelah itu WF1 n8n mendeteksi
dokumen baru setiap hari. Alurnya sama dengan WF1:

  halaman JDIH -> halaman detail (judul + status) -> unduh PDF resmi
  -> ekstrak teks asli (tanpa ditulis ulang AI) -> potong 1.000 karakter
  -> embedding OpenAI -> upsert Pinecone dengan metadata
  -> lapor status ke backend (POST /api/v1/admin/ingestion/callback)

Contoh:
  python -m scripts.ingest_jdih_awal --pages 2 \
      --backend https://ai-agent-kpu-api.vercel.app

Variabel yang dibutuhkan: OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME,
PINECONE_NAMESPACE, INGESTION_CALLBACK_SECRET.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
import time
import uuid
from html import unescape
from urllib.parse import urljoin

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from pinecone import Pinecone
from pypdf import PdfReader

JDIH = "https://jdih.kpu.go.id"
DETAIL_RE = re.compile(r'href="(https://jdih\.kpu\.go\.id/peraturan-kpu/detail/[^"]+)"')
PDF_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', re.I)
TITLE_RE = re.compile(
    r"((?:Peraturan|Keputusan) Komisi Pemilihan Umum Nomor \d+ Tahun \d{4} tentang .+?)"
    r"\s+Tipe Dokumen\s*:",
    re.I,
)
STATUS_RE = re.compile(
    r"status(?:\s+(?:peraturan|dokumen|hukum))?\s*:?\s*(tidak\s+berlaku|dicabut|berlaku|diubah)",
    re.I,
)
WORKFLOW = "Ingest awal JDIH"


def plain(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def legal_status(text: str) -> str:
    match = STATUS_RE.search(text)
    if not match:
        return "belum_diverifikasi"
    value = re.sub(r"\s+", " ", match.group(1).lower())
    if value == "berlaku":
        return "berlaku"
    if value == "diubah":
        return "belum_diverifikasi"
    return "tidak_berlaku"


def detail_urls(client: httpx.Client, pages: int) -> list[str]:
    urls: list[str] = []
    sources = [JDIH + "/"] + [
        f"{JDIH}/peraturan-kpu?page_peraturan={page}" for page in range(1, pages + 1)
    ]
    for source in sources:
        html = client.get(source).text
        for url in DETAIL_RE.findall(html):
            if url not in urls:
                urls.append(url)
    return urls


def read_detail(client: httpx.Client, url: str) -> list[dict]:
    html = client.get(url).text
    text = plain(html)
    title_match = TITLE_RE.search(text)
    title = title_match.group(1).strip()[:500] if title_match else None
    status = legal_status(text)
    number = year = None
    if title:
        found = re.search(r"Nomor (\d+) Tahun (\d{4})", title)
        if found:
            number, year = found.group(1), int(found.group(2))
    docs = []
    for raw in PDF_RE.findall(html):
        pdf_url = urljoin(JDIH + "/", raw.replace("&amp;", "&"))
        if re.search(r"_english\.pdf$", pdf_url, re.I):
            continue  # versi terjemahan tidak diindeks
        if pdf_url.startswith(JDIH + "/data/data_pkpu/") and pdf_url not in {d["pdf_url"] for d in docs}:
            docs.append({
                "pdf_url": pdf_url, "title": title, "legal_status": status,
                "document_type": "PKPU", "document_number": number, "year": year,
                "detail_url": url,
            })
    return docs


def callback(client: httpx.Client, backend: str, secret: str, payload: dict) -> None:
    response = client.post(
        backend.rstrip("/") + "/api/v1/admin/ingestion/callback",
        json=payload, headers={"X-Ingestion-Key": secret}, timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"callback HTTP {response.status_code}: {response.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pages", type=int, default=2, help="jumlah halaman daftar PKPU")
    parser.add_argument("--limit", type=int, default=25, help="maksimum dokumen diproses")
    parser.add_argument("--backend", required=True, help="URL backend FastAPI")
    args = parser.parse_args()

    namespace = os.environ["PINECONE_NAMESPACE"]
    secret = os.environ["INGESTION_CALLBACK_SECRET"]
    openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    pinecone_options = {}
    if os.environ.get("HTTPS_PROXY"):  # SDK Pinecone tidak membaca proxy dari environment
        pinecone_options["proxy_url"] = os.environ["HTTPS_PROXY"]
        if os.environ.get("SSL_CERT_FILE"):
            pinecone_options["ssl_ca_certs"] = os.environ["SSL_CERT_FILE"]
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"], **pinecone_options).Index(
        os.environ["PINECONE_INDEX_NAME"]
    )
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    execution_id = f"awal-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    with httpx.Client(timeout=120, follow_redirects=True,
                      headers={"User-Agent": "KPU-AI-Agent-Ingestion/1.0"}) as client:
        documents: list[dict] = []
        for url in detail_urls(client, args.pages):
            for doc in read_detail(client, url):
                if doc["pdf_url"] not in {d["pdf_url"] for d in documents}:
                    documents.append(doc)
        documents = documents[: args.limit]
        print(f"{len(documents)} PDF Peraturan KPU ditemukan; execution {execution_id}")

        for n, doc in enumerate(documents, 1):
            document_id = "jdih-" + hashlib.sha256(doc["pdf_url"].encode()).hexdigest()
            label = doc["title"] or doc["pdf_url"]
            base = {
                "workflow": WORKFLOW, "execution_id": f"{execution_id}-{n}",
                "document_id": document_id, "source_url": doc["pdf_url"],
                "document_type": doc["document_type"], "document_number": doc["document_number"],
                "title": doc["title"], "year": doc["year"], "namespace": namespace,
            }
            try:
                pdf = client.get(doc["pdf_url"])
                pdf.raise_for_status()
                file_hash = hashlib.sha256(pdf.content).hexdigest()
                callback(client, args.backend, secret,
                         {**base, "status": "processing", "file_hash": file_hash})
                reader = PdfReader(io.BytesIO(pdf.content))
                text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
                if len(text) < 200:
                    raise RuntimeError("PDF tidak memiliki teks yang dapat diekstrak (kemungkinan hasil scan)")
                chunks = [c for c in splitter.split_text(text) if c.strip()]
                metadata = {
                    "source_url": doc["pdf_url"], "document_id": document_id,
                    "title": doc["title"] or "", "document_type": doc["document_type"],
                    "document_number": doc["document_number"] or "", "year": doc["year"] or "",
                    "legal_status": doc["legal_status"], "file_hash": file_hash,
                }
                for start in range(0, len(chunks), 100):
                    batch = chunks[start:start + 100]
                    vectors = openai.embeddings.create(
                        model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                        input=batch,
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
                print(f"[{n}/{len(documents)}] OK {len(chunks)} chunk, {len(pasal)} pasal "
                      f"({doc['legal_status']}): {label[:90]}")
            except Exception as exc:  # dicatat ke dashboard admin sebagai failed
                print(f"[{n}/{len(documents)}] GAGAL {type(exc).__name__}: {exc} :: {label[:90]}")
                try:
                    callback(client, args.backend, secret, {**base, "status": "failed"})
                except Exception as cb_exc:
                    print("   callback failed juga gagal:", cb_exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
