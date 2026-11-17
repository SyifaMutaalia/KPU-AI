"""Batch PDF ingestion for KPU official documents, initially CLI; n8n can call later.

Preview:
  python -m scripts.ingest_pdfs --manifest data/kpu_manifest.csv --dry-run --limit 5
Upload (after validation):
  python -m scripts.ingest_pdfs --manifest data/kpu_manifest.csv --confirm-upload

Process runs outside public API. Keep ingestion state and original PDFs backed up.
"""
from __future__ import annotations

import argparse
import json
import os
import hashlib
from collections import Counter
from pathlib import Path

from app.core.config import get_settings
from app.rag.pdf_catalog import read_catalog
from app.rag.pdf_chunks import build_chunks, fingerprint


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "documents": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("documents"), dict):
        raise ValueError("Format ingestion state tidak dikenal; jangan lanjutkan unggah")
    return payload


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF -> LangChain chunks -> embeddings -> Pinecone")
    parser.add_argument("--manifest", type=Path, default=Path("data/kpu_manifest.csv"))
    parser.add_argument("--documents-root", type=Path, default=Path("data/kpu_documents"))
    parser.add_argument("--state-file", type=Path, default=Path("data/ingestion_state.json"))
    parser.add_argument("--dry-run", action="store_true", help="Tanpa API embeddings atau unggah Pinecone")
    parser.add_argument("--check-manifest", action="store_true", help="Validasi metadata saja; tanpa LangChain")
    parser.add_argument("--confirm-upload", action="store_true", help="Unggah ke Pinecone")
    parser.add_argument("--limit", type=int, default=0, help="Uji N dokumen teratas, 0 = semua")
    parser.add_argument("--expect-keputusan", type=int, default=0)
    parser.add_argument("--expect-pkpu", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    args = parser.parse_args()
    if args.limit < 0 or args.chunk_size < 300 or args.chunk_size > 3000 or not (0 <= args.chunk_overlap < args.chunk_size):
        parser.error("Parameter limit/chunk_size/chunk_overlap tidak valid")
    if not (args.dry_run or args.check_manifest or args.confirm_upload):
        parser.error("Pilih --check-manifest, --dry-run, atau --confirm-upload")
    if args.confirm_upload and (args.dry_run or args.check_manifest):
        parser.error("Mode unggah tidak boleh digabung dengan mode preview")

    s = get_settings()
    catalog = read_catalog(args.manifest, args.documents_root, s.rag_allowed_hosts)
    print(f"Manifest tervalidasi: {len(catalog)} dokumen (semua status)")
    print("Kategori:", dict(Counter(e.document_type for e in catalog)))
    print("Status:", dict(Counter(e.legal_status for e in catalog)))
    type_counts = Counter(e.document_type for e in catalog)
    if args.expect_keputusan and type_counts["keputusan_kpu_subang"] != args.expect_keputusan:
        raise ValueError(f"Jumlah keputusan {type_counts['keputusan_kpu_subang']} tidak sesuai target {args.expect_keputusan}")
    if args.expect_pkpu and type_counts["pkpu"] != args.expect_pkpu:
        raise ValueError(f"Jumlah PKPU {type_counts['pkpu']} tidak sesuai target {args.expect_pkpu}")
    if args.check_manifest:
        return
    selected = [e for e in catalog if e.legal_status == "berlaku"]
    skipped = len(catalog) - len(selected)
    print(f"Untuk RAG publik: {len(selected)} dokumen berlaku; {skipped} belum layak/berstatus lain")
    if args.limit:
        selected = selected[:args.limit]
    state = load_state(args.state_file)
    target = {"index": s.pinecone_index_name, "namespace": s.pinecone_namespace,
              "embedding_model": s.openai_embedding_model}
    if args.confirm_upload:
        if state.get("target") and state["target"] != target:
            raise ValueError("Ingestion state berasal dari index/namespace/model lain. Buat state file terpisah.")
        state["target"] = target
    store = None
    index = None
    if args.confirm_upload:
        if not (s.openai_api_key and s.pinecone_api_key and s.pinecone_index_name):
            raise RuntimeError("OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME wajib diisi")
        from pinecone import Pinecone
        from app.rag.store import get_vectorstore
        store = get_vectorstore()
        index = Pinecone(api_key=s.pinecone_api_key).Index(s.pinecone_index_name)

    stats = Counter()
    for entry in selected:
        current_version = hashlib.sha256(
            f"{fingerprint(entry)}|{args.chunk_size}|{args.chunk_overlap}".encode("utf-8")
        ).hexdigest()
        previous = state["documents"].get(entry.document_id)
        if previous and previous.get("fingerprint") == current_version and args.confirm_upload:
            stats["unchanged"] += 1
            continue
        docs, ids, blank = build_chunks(entry, current_version,
            chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
        stats["chunks"] += len(docs)
        stats["blank_pages"] += blank
        stats["processed"] += 1
        print(f"{entry.document_type} {entry.document_number}/{entry.year}: {len(docs)} chunks; {blank} halaman minim teks")
        if args.dry_run:
            continue
        # Upload new version first. Crash/retry stays idempotent because IDs are deterministic.
        for i in range(0, len(docs), 50):
            store.add_documents(documents=docs[i:i + 50], ids=ids[i:i + 50])
        # Delete only prior IDs known in saved state, after successful upload.
        # If upload stops midway, rerun: partial new chunks will be overwritten by same IDs.
        if previous and previous.get("ids"):
            new_ids = set(ids)
            old_ids = [value for value in previous["ids"] if value not in new_ids]
            for i in range(0, len(old_ids), 500):
                index.delete(ids=old_ids[i:i + 500], namespace=s.pinecone_namespace)
        state["documents"][entry.document_id] = {"fingerprint": current_version, "ids": ids,
            "source_url": entry.source_url, "legal_status": entry.legal_status}
        save_state(args.state_file, state)
        stats["uploaded"] += 1
    # Revoke previously indexed documents explicitly marked non-current in manifest.
    # Never remove a record solely because it disappeared from the local CSV.
    if args.confirm_upload and not args.limit:
        for entry in catalog:
            if entry.legal_status == "berlaku":
                continue
            previous = state["documents"].get(entry.document_id)
            if not previous:
                continue
            old_ids = previous.get("ids") or []
            for i in range(0, len(old_ids), 500):
                index.delete(ids=old_ids[i:i + 500], namespace=s.pinecone_namespace)
            del state["documents"][entry.document_id]
            save_state(args.state_file, state)
            stats["revoked_from_index"] += 1
    print("Selesai:", dict(stats))
    print("INFO: PDF scan tanpa teks harus melalui OCR terverifikasi sebelum ingestion.")
    if args.dry_run:
        print("Dry-run: tidak melakukan panggilan embedding dan tidak menulis Pinecone.")


if __name__ == "__main__":
    main()
