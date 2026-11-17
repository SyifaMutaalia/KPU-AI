"""Controlled ingestion of reviewed, official KPU documents into Pinecone.

Usage:
  python -m scripts.ingest_json examples/approved_documents.example.json --dry-run
  python -m scripts.ingest_json path/to/reviewed.json --confirm-replace

Ingestion is intentionally an operator task, not a public API. n8n may prepare
reviewed JSON, then an internal deployment job runs this script after approval.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone

from app.core.config import get_settings
from app.core.safety import is_approved_source
from app.rag.store import get_vectorstore


def prepare_documents(path: Path) -> tuple[list[Document], list[str], list[str]]:
    s = get_settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("File harus JSON array berisi dokumen yang telah diverifikasi.")
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=130)
    chunks, ids, document_ids = [], [], []
    for entry in data:
        url = entry["source_url"]
        title = entry["title"].strip()
        text = entry["text"].strip()
        if not is_approved_source(url, s.rag_allowed_hosts):
            raise ValueError(f"Domain sumber tidak diizinkan: {url}")
        if not title or len(title) > 160 or len(text) < 40 or len(text) > 2_000_000:
            raise ValueError(f"Dokumen tidak valid: {url}")
        document_id = hashlib.sha256(url.encode()).hexdigest()
        if document_id in document_ids:
            raise ValueError(f"Dokumen duplikat: {url}")
        document_ids.append(document_id)
        now = datetime.now(timezone.utc).isoformat()
        for i, piece in enumerate(splitter.split_text(text)):
            ids.append(f"{document_id}-{i:05d}")
            chunks.append(Document(page_content=piece, metadata={
                "source_url": url,
                "title": title,
                "document_id": document_id,
                "ingested_at": now,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }))
    return chunks, ids, document_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Masukkan dokumen KPU yang sudah diverifikasi ke Pinecone")
    parser.add_argument("file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-replace", action="store_true")
    args = parser.parse_args()
    chunks, ids, document_ids = prepare_documents(args.file)
    print(f"Validated {len(document_ids)} documents -> {len(chunks)} chunks")
    if args.dry_run:
        return
    if not args.confirm_replace:
        parser.error("Untuk mengganti isi dokumen, gunakan --confirm-replace setelah pemeriksaan.")
    s = get_settings()
    if not (s.pinecone_api_key and s.pinecone_index_name):
        raise RuntimeError("PINECONE_API_KEY dan PINECONE_INDEX_NAME diperlukan.")
    # NOTE: this is NOT atomic: if upload fails after deletion, re-run ingestion.
    # Restrict this script's execution to trusted operators and keep a document backup.
    index = Pinecone(api_key=s.pinecone_api_key).Index(s.pinecone_index_name)
    for document_id in document_ids:
        index.delete(filter={"document_id": {"$eq": document_id}}, namespace=s.pinecone_namespace)
    store = get_vectorstore()
    for i in range(0, len(chunks), 50):
        store.add_documents(chunks[i:i + 50], ids=ids[i:i + 50])
    print("Ingestion complete. Verify search relevance and current legal status before publishing.")


if __name__ == "__main__":
    main()
