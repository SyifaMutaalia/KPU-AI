"""Suggest legal chunk boundaries using LLM, copy original Markdown EXACTLY.

The LLM chooses inclusive line ranges. Python slices the original Markdown,
so the model cannot silently rewrite the chunk text.

Run:
python -m scripts.llm_chunk_markdown --markdown data/extracted_markdown/2018kpt1264/pages-003-003.verified.md --confirm-send
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, Field


PAGE_MARKER = re.compile(r"<!-- PAGE:\s*(\d+)\s*-->")


class LegalBoundary(BaseModel):
    start_line: int = Field(description="Nomor baris mulai, inklusif, mulai dari 1")
    end_line: int = Field(description="Nomor baris akhir, inklusif")
    unit_type: str = Field(description="pasal/diktum/lampiran_tabel/metadata/other")
    legal_reference: str = Field(description="Label hukum literal, mis. Pasal 3 atau KESATU")
    needs_review: bool = Field(description="True jika cakupan/isi ambigu, lanjutan lintas halaman, atau tidak lengkap")
    review_note: str = Field(description="Catatan singkat untuk peninjau, string kosong jika tidak ada")


class BoundaryPlan(BaseModel):
    chunks: list[LegalBoundary]


CHUNK_INSTRUCTIONS = """Anda editor struktur dokumen hukum Indonesia.
Anda akan menerima Markdown dengan SETIAP BARIS DINOMORI secara eksplisit.
Tentukan batas chunk, BUKAN isi chunk. Kembalikan hanya data terstruktur.
Aturan wajib:
1) Semua baris 1..N harus terliput tepat satu kali, berurutan, tanpa celah/overlap.
2) Satu Pasal UTUH = satu chunk, termasuk ayat/hurufnya. Jangan memotong Pasal
   berdasarkan panjang karakter. Satu diktum (KESATU, KEDUA...) = satu chunk.
3) Gabungkan kelanjutan Pasal/diktum yang melintasi penanda halaman jika ada.
4) Tabel jangan dipecah dalam tengah baris tabel. Usahakan kelompok per tabel
   atau bagian/kelompok administratif yang utuh.
5) Teks pembuka, judul, dan bagian di luar Pasal/diktum tetap harus tercakup.
6) Penanda <!-- PAGE: N --> bukan batas chunk hukum otomatis.
7) Bila hanya diberi sebagian halaman, jangan berpura-pura dokumen lengkap;
   tandai needs_review=True pada unit yang mungkin terpotong.
8) legal_reference berasal dari label yang benar-benar ada; jika tidak ada,
   berikan string kosong. Jangan mengarang nomor atau isi.
"""


def verify_boundaries(plan: BoundaryPlan, line_count: int) -> None:
    if not plan.chunks:
        raise ValueError("LLM tidak memberikan batas chunk")
    expected = 1
    for item in plan.chunks:
        if item.start_line != expected or item.end_line < expected or item.end_line > line_count:
            raise ValueError(
                f"Batas LLM tidak valid. Seharusnya mulai {expected}, "
                f"mendapat {item.start_line}..{item.end_line}, total {line_count}"
            )
        expected = item.end_line + 1
    if expected != line_count + 1:
        raise ValueError(f"LLM melewatkan baris {expected}..{line_count}")


def build_preview(markdown: str, source_file: str, plan: BoundaryPlan, model: str) -> dict:
    lines = markdown.splitlines(keepends=True)
    verify_boundaries(plan, len(lines))
    raw_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    page_map: list[int | None] = []
    page = None
    for line in lines:
        match = PAGE_MARKER.search(line)
        if match:
            page = int(match.group(1))
        page_map.append(page)

    chunks = []
    for idx, item in enumerate(plan.chunks, 1):
        content = "".join(lines[item.start_line - 1:item.end_line])
        if not content.strip():
            raise ValueError(f"Chunk {idx} kosong")
        pages = sorted({p for p in page_map[item.start_line - 1:item.end_line] if p is not None})
        stable_id = hashlib.sha256(
            f"{raw_sha}|{item.start_line}|{item.end_line}".encode("utf-8")
        ).hexdigest()[:24]
        chunks.append({
            "id": f"kpu-draft-{stable_id}",
            "unit_type": item.unit_type,
            "legal_reference": item.legal_reference,
            "start_line": item.start_line,
            "end_line": item.end_line,
            "pages": pages,
            "text_md": content,
            "needs_review": item.needs_review,
            "review_note": item.review_note,
            "review_status": "pending_manual_verification",
        })

    # Zero text loss: no LLM-generated paraphrase enters the vector content.
    if "".join(chunk["text_md"] for chunk in chunks) != markdown:
        raise ValueError("Invariant gagal: teks chunk tidak identik dengan sumber")
    return {
        "schema_version": 1,
        "source_markdown": source_file,
        "source_markdown_sha256": raw_sha,
        "model": model,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending_manual_verification",
        "pinecone_uploaded": False,
        "chunks": chunks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM legal chunk boundaries -> JSON preview; no Pinecone")
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--allow-draft", action="store_true", help="Preview hanya; untuk evaluasi draf belum diperiksa")
    parser.add_argument("--confirm-send", action="store_true", help="Izinkan Markdown dikirim ke API eksternal")
    args = parser.parse_args()
    if not args.markdown.is_file() or args.markdown.suffix.lower() != ".md":
        parser.error("File Markdown tidak ditemukan")
    if not args.confirm_send:
        parser.error("Dokumen akan dikirim ke API eksternal; tambahkan --confirm-send jika diizinkan")
    if not args.allow_draft and not args.markdown.name.endswith(".verified.md"):
        parser.error("Gunakan .verified.md setelah pemeriksaan; atau --allow-draft hanya untuk preview")
    markdown = args.markdown.read_text(encoding="utf-8")
    lines = markdown.splitlines(keepends=True)
    if not lines or not markdown.strip():
        parser.error("Markdown kosong")
    if len(lines) > 650 or len(markdown) > 65000:
        parser.error("Pilot dibatasi 450 baris/45k karakter; bagi per unit dokumen terverifikasi, jangan potong Pasal")
    config = dotenv_values(".env")
    key = config.get("OPENAI_API_KEY")
    if not key:
        parser.error("OPENAI_API_KEY tidak ada di .env backend")

    numbered = "\n".join(f"{i:04d} | {line.rstrip(chr(10)).rstrip(chr(13))}"
                         for i, line in enumerate(lines, 1))
    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=180, max_retries=1)
    response = client.responses.parse(
        model=args.model,
        store=False,
        instructions=CHUNK_INSTRUCTIONS,
        input=f"Jumlah baris: {len(lines)}\n\n{numbered}",
        text_format=BoundaryPlan,
        max_output_tokens=7000,
    )
    plan = response.output_parsed
    if plan is None:
        raise RuntimeError("Output terstruktur tidak tersedia; chunking tidak disimpan")
    payload = build_preview(markdown, args.markdown.as_posix(), plan, args.model)
    output = args.output or args.markdown.with_suffix(".chunks.preview.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Berhasil membuat {len(payload['chunks'])} chunk preview: {output}")
    for i, chunk in enumerate(payload["chunks"], 1):
        print(f"{i:02d}. {chunk['unit_type']} | {chunk['legal_reference']} | "
              f"baris {chunk['start_line']}-{chunk['end_line']} | halaman {chunk['pages']}")
    print("Periksa terhadap PDF asli. Tidak ada data dikirim ke Pinecone.")


if __name__ == "__main__":
    main()
