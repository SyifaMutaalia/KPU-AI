"""Prepare a blank, review-required inventory for locally supplied KPU PDFs.

Does not crawl, guess document numbers/years, or assert legal validity.
After generation, complete and verify every CSV record before ingestion.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from app.rag.pdf_catalog import ALLOWED_TYPES


FIELDS = ["file_path", "document_type", "document_number", "year", "title",
          "source_url", "legal_status", "issued_date"]


def create_manifest(documents_root: Path, output: Path) -> dict[str, int]:
    root = documents_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Folder dokumen tidak ditemukan")
    rows = []
    counters = Counter()
    for pdf in sorted(root.rglob("*.pdf")):
        if pdf.is_symlink() or not pdf.resolve().is_relative_to(root):
            continue
        rel = pdf.relative_to(root)
        if len(rel.parts) < 2 or rel.parts[0] not in ALLOWED_TYPES:
            raise ValueError(f"PDF berada di folder kategori yang salah: {rel}")
        kind = rel.parts[0]
        counters[kind] += 1
        rows.append({"file_path": rel.as_posix(), "document_type": kind,
                     "document_number": "", "year": "", "title": "",
                     "source_url": "", "legal_status": "belum_diverifikasi", "issued_date": ""})
    if not rows:
        raise ValueError("Tidak ditemukan PDF di folder kategori")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Create-only prevents accidental loss of manual review work.
    with output.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return dict(counters)


def main() -> None:
    parser = argparse.ArgumentParser(description="Buat manifest CSV awal tanpa mengarang metadata")
    parser.add_argument("--documents-root", type=Path, default=Path("data/kpu_documents"))
    parser.add_argument("--output", type=Path, default=Path("data/kpu_manifest.csv"))
    args = parser.parse_args()
    results = create_manifest(args.documents_root, args.output)
    print("Draft manifest dibuat:", args.output)
    print("Kategori:", results)
    print("ISI dan VERIFIKASI nomor, tahun, judul, URL detail sumber dan status sebelum ingestion.")


if __name__ == "__main__":
    main()
