"""Preview one PDF without manifest, Neon, OpenAI or Pinecone.

Usage: python -m scripts.preview_one_pdf --pdf data/kpu_doc/kpu_jdih/NAME.pdf
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader
from app.rag.pdf_chunks import parse_legal_sections, MAX_UNIT_CHARS, MAX_UNIT_BYTES


def preview(pdf: Path, output_dir: Path) -> Path:
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        raise ValueError(f"PDF tidak ditemukan: {pdf}")
    reader = PdfReader(str(pdf), strict=False)
    if reader.is_encrypted:
        raise ValueError("PDF terenkripsi")
    pages = [(i, (page.extract_text(extraction_mode="plain") or "").strip())
             for i, page in enumerate(reader.pages, start=1)]
    blank = [i for i, text in pages if len(text) < 20]
    sections = parse_legal_sections(pages)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / (pdf.stem + "_legal_preview.txt")
    result = [
        f"PDF: {pdf}",
        f"JUMLAH HALAMAN: {len(pages)}",
        f"JUMLAH UNIT: {len(sections)}",
        f"HALAMAN MINIM TEKS (PERLU REVIEW): {blank}",
        "PERINGATAN: Preview belum berarti dokumen valid untuk diunggah. Periksa PDF asli.",
    ]
    for i, s in enumerate(sections, start=1):
        oversized = len(s.text)>MAX_UNIT_CHARS or len(s.text.encode('utf-8'))>MAX_UNIT_BYTES
        result += [
            "\n" + "=" * 72,
            f"UNIT {i}: {s.kind.upper()} — {s.label}",
            f"HALAMAN {s.page_start}–{s.page_end}; BAB: {s.chapter or '-'}; PANJANG: {len(s.text)} karakter",
            f"REVIEW: {'WAJIB (unit terlalu panjang)' if oversized else 'bandingkan dengan PDF asli'}",
            "=" * 72,
            s.text,
        ]
    out.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"Hasil preview: {out}")
    print(f"Total unit: {len(sections)}, halaman minim teks: {len(blank)}")
    if blank:
        print("PERHATIAN: halaman minim teks harus diverifikasi, jangan upload dulu.")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/legal_preview"))
    args = parser.parse_args()
    preview(args.pdf, args.output_dir)


if __name__ == "__main__":
    main()
