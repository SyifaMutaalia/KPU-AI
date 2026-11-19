"""Conservative upload of reviewed LLM legal chunks to an isolated Pinecone namespace.

This is a STAGING uploader, not a publication or legal-status validation tool.
Run from the KPU_AI_Agent_Terintegrasi project root.

Preview:
  python -m scripts.ingest_verified_pinecone --chunk-json \
    data/extracted_markdown/2024kpt4/pages-001-003.verified.chunks.preview.json
Upload after manually inspecting PDF, Markdown, and chunk boundaries:
  python -m scripts.ingest_verified_pinecone --chunk-json ... \
    --confirm-reviewed --confirm-upload
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from dotenv import dotenv_values
from langchain_core.documents import Document

DEFAULT_NAMESPACE = "kpu_review_2024_2026"
CHUNK_LIMIT_BYTES = 25_000  # Keep Pinecone's per-record metadata comfortably below its cap.
CHUNK_LIMIT_TOKENS = 7_000  # Embedding requests have a model-specific input token cap.


def discover_previews(root: Path, include_2017: bool = False) -> list[Path]:
    paths = sorted(root.glob("*/pages-*.verified.chunks.preview.json"))
    if not include_2017:
        paths = [p for p in paths if re.search(r"202[456]", p.parent.name)]
    return paths


def source_path_for(payload: dict, json_path: Path) -> Path:
    # Derived from the preview file name to avoid relying on old absolute Windows paths.
    name = json_path.name
    suffix = ".chunks.preview.json"
    if not name.endswith(suffix):
        raise ValueError(f"File harus berakhir dengan {suffix}: {json_path}")
    local = json_path.with_name(name[: -len(suffix)] + ".md")
    if not local.is_file() or not local.name.endswith(".verified.md"):
        raise FileNotFoundError(f"Markdown terverifikasi tidak ditemukan: {local}")
    return local


def validate_preview(json_path: Path) -> tuple[list[Document], list[str], str]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    md_path = source_path_for(payload, json_path)
    markdown = md_path.read_text(encoding="utf-8")
    actual_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if payload.get("source_markdown_sha256") != actual_sha:
        raise ValueError(f"Checksum tidak cocok: {md_path}. Chunk ulang dari Markdown terbaru.")

    chunks = payload.get("chunks") or []
    if not chunks:
        raise ValueError(f"Daftar chunks kosong: {json_path}")
    if "".join(c.get("text_md", "") for c in chunks) != markdown:
        raise ValueError(f"Teks chunk tidak sama persis dengan file Markdown: {json_path}")

    folder = md_path.parent.name
    year_match = re.search(r"(20\d{2})", folder)
    year = int(year_match.group(1)) if year_match else 0
    doc_type = (
        "undang_undang" if "uu" in folder.lower() else
        "pkpu" if "pkpu" in folder.lower() or "peraturan kpu" in folder.lower() else
        "keputusan" if "kpt" in folder.lower() else "belum_diklasifikasi"
    )
    docs: list[Document] = []
    ids: list[str] = []
    expected_line = 1
    import tiktoken
    encoder = tiktoken.encoding_for_model("text-embedding-3-small")
    for idx, chunk in enumerate(chunks, 1):
        text = chunk.get("text_md") or ""
        start, end = chunk.get("start_line"), chunk.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int) or start != expected_line or end < start:
            raise ValueError(f"Rentang baris chunk {idx} tidak berurutan: {json_path}")
        expected_line = end + 1
        pages = chunk.get("pages") or []
        pages = [int(p) for p in pages]
        label = str(chunk.get("legal_reference") or "").strip()
        content = (
            f"Dokumen: {folder}\n"
            f"Bagian: {label or 'Bagian tanpa label'}\n"
            f"Halaman: {', '.join(map(str, pages)) if pages else 'tidak terdeteksi'}\n\n"
            f"{text}"
        )
        if len(content.encode("utf-8")) > CHUNK_LIMIT_BYTES:
            raise ValueError(
                f"Chunk {idx} ({folder}, {label}) terlalu besar untuk disimpan aman. "
                "Jangan memotong Pasal/diktum; gunakan parent-child retrieval."
            )
        if len(encoder.encode(content)) > CHUNK_LIMIT_TOKENS:
            raise ValueError(
                f"Chunk {idx} ({folder}, {label}) melebihi batas embedding. "
                "Jangan memotong Pasal/diktum; gunakan parent-child retrieval."
            )
        digest = hashlib.sha256((folder + "|" + str(start) + "|" + str(end) + "|" + actual_sha).encode()).hexdigest()[:28]
        record_id = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', folder)[:45]}-{digest}"
        ids.append(record_id)
        docs.append(Document(page_content=content, metadata={
            "document_id": folder,
            "document_type": doc_type,
            "year": year,
            "source_file": md_path.as_posix(),
            "source_sha256": actual_sha,
            "source_url": "",  # Intentionally blank until original official URL is validated.
            "title": folder,      # Staging label, not an invented legal title.
            "unit_type": str(chunk.get("unit_type") or ""),
            "legal_reference": label,
            "page_start": min(pages) if pages else -1,
            "page_end": max(pages) if pages else -1,
            "legal_status": "belum_diverifikasi",  # NOT equivalent to Markdown verification.
            "chunk_review_status": "manually_reviewed_for_staging",
            "needs_review_from_llm": bool(chunk.get("needs_review", False)),
        }))
    line_count = len(markdown.splitlines(keepends=True))
    if expected_line != line_count + 1:
        raise ValueError(f"Coverage baris gagal: {json_path}")
    return docs, ids, folder


def upload(docs: list[Document], ids: list[str], namespace: str) -> None:
    config = dotenv_values(".env")
    openai_key = config.get("OPENAI_API_KEY")
    pinecone_key = config.get("PINECONE_API_KEY")
    index_name = config.get("PINECONE_INDEX_NAME")
    embedding_model = config.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    if not all((openai_key, pinecone_key, index_name)):
        raise ValueError("OPENAI_API_KEY, PINECONE_API_KEY, dan PINECONE_INDEX_NAME harus ada di .env")
    if embedding_model != "text-embedding-3-small":
        raise ValueError("Pilot ini memerlukan OPENAI_EMBEDDING_MODEL=text-embedding-3-small (1536 dimensi)")
    from pinecone import Pinecone
    from langchain_openai import OpenAIEmbeddings
    from langchain_pinecone import PineconeVectorStore

    pc = Pinecone(api_key=pinecone_key)
    info = pc.describe_index(index_name)
    dimension = getattr(info, "dimension", None)
    metric = getattr(info, "metric", None)
    if dimension != 1536 or metric != "cosine":
        raise ValueError(f"Index {index_name} memiliki dimension={dimension}, metric={metric}; diharapkan 1536/cosine")
    embedding = OpenAIEmbeddings(model=embedding_model, api_key=openai_key)
    store = PineconeVectorStore(
        index_name=index_name,
        embedding=embedding,
        pinecone_api_key=pinecone_key,
        namespace=namespace,
    )
    for start in range(0, len(docs), 16):
        batch = docs[start:start + 16]
        batch_ids = ids[start:start + 16]
        store.add_documents(documents=batch, ids=batch_ids)
        print(f"  Berhasil mengunggah {start + len(batch)}/{len(docs)} chunks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verified Markdown chunks -> Pinecone STAGING namespace")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--chunk-json", type=Path, help="Output dari llm_chunk_markdown.py")
    choice.add_argument("--all", action="store_true", help="Semua preview tersedia untuk 2024-2026")
    parser.add_argument("--root", type=Path, default=Path("data/extracted_markdown"))
    parser.add_argument("--include-2017", action="store_true", help="Termasuk UU 2017, bila chunk JSON telah disiapkan dan diperiksa")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--confirm-reviewed", action="store_true", help="Saya sudah memeriksa batas chunk terhadap PDF/verified.md")
    parser.add_argument("--confirm-upload", action="store_true", help="Izinkan embedding berbayar dan tulis ke Pinecone")
    args = parser.parse_args()

    if args.namespace == dotenv_values(".env").get("PINECONE_NAMESPACE", "kpu-subang"):
        parser.error("Namespace harus berbeda dari namespace live agar dokumen yang belum dicek status hukum tidak muncul pada chat")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,128}", args.namespace):
        parser.error("Nama namespace tidak valid; gunakan huruf/angka/_/-")
    paths = discover_previews(args.root, args.include_2017) if args.all else [args.chunk_json]
    if not paths:
        parser.error("Belum ada file .verified.chunks.preview.json; jalankan llm_chunk_markdown terlebih dahulu")
    all_docs: list[Document] = []
    all_ids: list[str] = []
    for path in paths:
        docs, ids, folder = validate_preview(path)
        all_docs.extend(docs)
        all_ids.extend(ids)
        print(f"[VALIDASI OK] {folder}: {len(docs)} chunk dari {path.name}")
        needs_review = [d.metadata['legal_reference'] for d in docs if d.metadata['needs_review_from_llm']]
        if needs_review:
            print(f"  [PERHATIAN] {len(needs_review)} chunk ditandai needs_review oleh LLM. Tinjau sebelum --confirm-reviewed")
    print(f"TOTAL: {len(all_docs)} chunks; namespace={args.namespace}; legal_status=belum_diverifikasi")
    if not args.confirm_upload:
        print("DRY RUN selesai: tidak ada API dipanggil, tidak ada data diunggah")
        return
    if not args.confirm_reviewed:
        parser.error("Untuk upload, tambahkan --confirm-reviewed HANYA setelah memeriksa batas semua chunk")
    upload(all_docs, all_ids, args.namespace)
    print("SELESAI: Vektor tersimpan di namespace STAGING. Belum digunakan oleh chat live.")


if __name__ == "__main__":
    main()
