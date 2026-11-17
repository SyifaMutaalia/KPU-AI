"""Curated PDF inventory, validated before LangChain ingestion.

This module deliberately does not crawl websites or trust PDF text as instructions.
All entries require a human-reviewed official source URL and legal status.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.core.safety import is_approved_source

ALLOWED_TYPES = frozenset({"keputusan_kpu_subang", "pkpu"})
LEGAL_STATUSES = frozenset({"berlaku", "diubah", "dicabut", "belum_diverifikasi"})
REQUIRED_FIELDS = {"file_path", "document_type", "document_number", "year", "title", "source_url", "legal_status"}


@dataclass(frozen=True)
class CatalogEntry:
    file_path: Path
    document_type: str
    document_number: str
    year: int
    title: str
    source_url: str
    legal_status: str
    issued_date: str
    document_id: str


def read_catalog(manifest: Path, documents_root: Path, allowed_hosts: list[str]) -> list[CatalogEntry]:
    """Reject unsupported types, path traversal, invalid metadata, and missing PDFs."""
    root = documents_root.resolve(strict=True)
    with manifest.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or REQUIRED_FIELDS.difference(reader.fieldnames):
            raise ValueError(f"Kolom manifest wajib: {', '.join(sorted(REQUIRED_FIELDS))}")
        catalog = []
        ids = set()
        for line, row in enumerate(reader, start=2):
            try:
                rel = (row.get("file_path") or "").strip().replace("\\", "/")
                path = (root / rel).resolve(strict=True)
                if not path.is_relative_to(root) or path.suffix.lower() != ".pdf":
                    raise ValueError("path harus PDF di dalam documents_root")
                if not path.is_file() or path.stat().st_size > 30 * 1024 * 1024:
                    raise ValueError("PDF hilang atau lebih dari 30 MB")
                kind = (row.get("document_type") or "").strip().lower()
                if kind not in ALLOWED_TYPES:
                    raise ValueError("document_type tidak dikenal")
                number = (row.get("document_number") or "").strip()
                if not 1 <= len(number) <= 100:
                    raise ValueError("nomor dokumen wajib diisi")
                year = int((row.get("year") or "").strip())
                if year < 1990 or year > 2100:
                    raise ValueError("tahun dokumen tidak valid")
                title = (row.get("title") or "").strip()
                if not 5 <= len(title) <= 300:
                    raise ValueError("judul dokumen tidak valid")
                url = (row.get("source_url") or "").strip()
                if not is_approved_source(url, allowed_hosts):
                    raise ValueError("URL bukan host resmi pada allowlist")
                status = (row.get("legal_status") or "").strip().lower()
                if status not in LEGAL_STATUSES:
                    raise ValueError("status harus berlaku/diubah/dicabut/belum_diverifikasi")
                date = (row.get("issued_date") or "").strip()
                if date:
                    from datetime import date as Date
                    Date.fromisoformat(date)
                # Include type and official URL for deterministic, collision-resistant identity.
                document_id = hashlib.sha256(f"{kind}|{url}".encode("utf-8")).hexdigest()[:32]
                if document_id in ids:
                    raise ValueError("URL/identitas dokumen terduplikasi")
                ids.add(document_id)
                catalog.append(CatalogEntry(path, kind, number, year, title, url, status, date, document_id))
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(f"Baris manifest {line}: {exc}") from exc
    if not catalog:
        raise ValueError("Manifest tidak berisi dokumen")
    return catalog


def pdf_pages(entry: CatalogEntry) -> Iterator[tuple[int, str]]:
    """Extract embedded text only; scanned PDFs require a separate OCR review step."""
    from pypdf import PdfReader
    reader = PdfReader(str(entry.file_path), strict=False)
    if reader.is_encrypted:
        raise ValueError(f"PDF terenkripsi, tidak bisa diproses: {entry.file_path.name}")
    if not 1 <= len(reader.pages) <= 1000:
        raise ValueError(f"Jumlah halaman tidak valid: {entry.file_path.name}")
    for i, page in enumerate(reader.pages, start=1):
        yield i, (page.extract_text(extraction_mode="plain") or "").strip()
