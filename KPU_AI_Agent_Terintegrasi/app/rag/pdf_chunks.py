"""Conservative structural chunking for PKPU and KPU decrees.

Never split a Pasal or numbered Keputusan dictum by character count or PDF page.
The output MUST be manually checked against the original PDF before indexing.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.rag.pdf_catalog import CatalogEntry, pdf_pages

PASAL = re.compile(r"^Pasal\s+(\d+[A-Za-z]?|[IVXLCDM]+)\s*[:.]?\s*$", re.IGNORECASE)
BAB = re.compile(r"^BAB\s+([IVXLCDM]+|\d+)\s*$", re.IGNORECASE)
BAGIAN = re.compile(r"^Bagian\s+(?:Ke[-\s]?\w+|[IVXLCDM]+|\d+)\s*$", re.IGNORECASE)
DIKTUM = re.compile(
    r"^(KESATU|KEDUA|KETIGA|KEEMPAT|KELIMA|KEENAM|KETUJUH|KEDELAPAN|"
    r"KESEMBILAN|KESEPULUH|KESEBELAS|KEDUA\s+BELAS|KETIGA\s+BELAS)\s*[:.]?\s*(.*)$",
)
PENJELASAN = re.compile(r"^PENJELASAN\s*$", re.IGNORECASE)
LAMPIRAN = re.compile(r"^LAMPIRAN(?:\s+[IVXLCDM\d]+)?\s*$", re.IGNORECASE)
MENIMBANG = re.compile(r"^Menimbang\s*[:.]?\s*$", re.IGNORECASE)
MENGINGAT = re.compile(r"^Mengingat\s*[:.]?\s*$", re.IGNORECASE)
MENETAPKAN = re.compile(r"^Menetapkan\s*[:.]?\s*$", re.IGNORECASE)
PENUTUP = re.compile(r"^(?:Ditetapkan\s+di|Ditetapkan\s+pada|Diundangkan\s+di|Diundangkan\s+pada)\b", re.IGNORECASE)
JDIH_FOOTER = re.compile(r"^(?:https?://)?(?:www\.)?jdih\.kpu\.go\.id/?$", re.IGNORECASE)
PAGE_NO = re.compile(r"^-\s*\d+\s*-$")
MAX_UNIT_CHARS = 14000
MAX_UNIT_BYTES = 26000


@dataclass(frozen=True)
class LegalSection:
    kind: str
    label: str
    chapter: str
    page_start: int
    page_end: int
    text: str


def fingerprint(entry: CatalogEntry) -> str:
    with entry.file_path.open("rb") as stream:
        file_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    reviewed = {
        "document_type": entry.document_type,
        "document_number": entry.document_number,
        "year": entry.year,
        "title": entry.title,
        "source_url": entry.source_url,
        "legal_status": entry.legal_status,
        "issued_date": entry.issued_date,
    }
    payload = file_hash + json.dumps(reviewed, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_legal_sections(pages: list[tuple[int, str]]) -> list[LegalSection]:
    """Parse full PDF across pages, preserving each Pasal/diktum uncut.

    Identifying a heading does not by itself establish legal correctness.
    Blank pages, multi-column layouts, annexes and tables need manual review.
    """
    sections: list[LegalSection] = []
    lines: list[str] = []
    kind, label, chapter = "pembuka", "Pembuka", ""
    page_start = page_end = 0
    found_normative_unit = False
    in_explanation = False

    def flush():
        if lines:
            content = "\n".join(lines).strip()
            if content:
                sections.append(LegalSection(kind, label, chapter, page_start, page_end, content))

    for page_num, content in pages:
        for raw_line in (content or "").splitlines():
            text = raw_line.strip()
            if not text or JDIH_FOOTER.fullmatch(text) or PAGE_NO.fullmatch(text):
                continue
            next_kind = next_label = None
            next_chapter = chapter
            if match := BAB.fullmatch(text):
                next_chapter = f"BAB {match.group(1)}"
                next_kind, next_label = "struktur", next_chapter
            elif BAGIAN.fullmatch(text):
                next_kind, next_label = "struktur", text
            elif PENJELASAN.fullmatch(text):
                next_kind, next_label = "penjelasan", "PENJELASAN"
                in_explanation = True
            elif LAMPIRAN.fullmatch(text):
                next_kind, next_label = "lampiran", text
                in_explanation = False
            elif match := PASAL.fullmatch(text):
                next_kind = "penjelasan_pasal" if in_explanation else "pasal"
                next_label = f"Pasal {match.group(1)}"
                if not in_explanation:
                    found_normative_unit = True
            elif match := DIKTUM.fullmatch(text):
                next_kind, next_label = "diktum", match.group(1).upper()
                found_normative_unit = True
            elif MENIMBANG.fullmatch(text):
                next_kind, next_label = "menimbang", "Menimbang"
            elif MENGINGAT.fullmatch(text):
                next_kind, next_label = "mengingat", "Mengingat"
            elif MENETAPKAN.fullmatch(text):
                next_kind, next_label = "menetapkan", "Menetapkan"
            elif PENUTUP.match(text):
                # Avoid mixing signatures into the final article/diktum.
                if kind not in {"pengesahan", "lampiran"}:
                    next_kind, next_label = "pengesahan", "Pengesahan/Pengundangan"

            if next_kind:
                flush()
                lines = []
                kind, label, chapter = next_kind, next_label, next_chapter
                page_start = page_num
            if not lines:
                page_start = page_num
            page_end = page_num
            lines.append(text)
    flush()
    if not found_normative_unit:
        raise ValueError(
            "Tidak ditemukan Pasal atau diktum keputusan. Periksa ekstraksi, format, atau OCR PDF sebelum ingestion."
        )
    return sections


def build_chunks(
    entry: CatalogEntry,
    version: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
):
    """Return LangChain Documents, deterministic Pinecone IDs, blank page count.

    The old CLI's chunk_size/chunk_overlap parameters remain for compatibility;
    they are NOT used to split legal sections. Oversized units fail closed.
    """
    from langchain_core.documents import Document

    raw_pages = list(pdf_pages(entry))
    blank_pages = sum(len(text.strip()) < 20 for _, text in raw_pages)
    if blank_pages:
        raise ValueError(
            f"{blank_pages} halaman minim teks pada {entry.file_path.name}. "
            "Tinjau halaman scan/kosong dan selesaikan ekstraksi sebelum upload Pinecone."
        )
    sections = parse_legal_sections(raw_pages)
    docs, ids = [], []
    now = datetime.now(timezone.utc).isoformat()
    for i, section in enumerate(sections):
        if len(section.text) > MAX_UNIT_CHARS or len(section.text.encode('utf-8')) > MAX_UNIT_BYTES:
            raise ValueError(
                f"Unit {section.label} melebihi batas ({len(section.text)} karakter). "
                "Perlu parent-child retrieval, jangan memotong unit hukum otomatis."
            )
        # Prefix legal identity for more grounded retrieval; original unit remains uncut.
        prefix = f"{entry.document_type} Nomor {entry.document_number} Tahun {entry.year}\n{entry.title}"
        content = "\n".join(filter(None, [prefix, section.chapter, section.text]))
        record_id = f"kpu-{entry.document_id}-{version[:16]}-u{i:04d}"
        docs.append(Document(page_content=content, metadata={
            "document_id": entry.document_id,
            "document_type": entry.document_type,
            "document_number": entry.document_number,
            "year": entry.year,
            "title": entry.title,
            "source_url": entry.source_url,
            "legal_status": entry.legal_status,
            "issued_date": entry.issued_date,
            "page": section.page_start,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "unit_kind": section.kind,
            "unit_label": section.label,
            "chapter": section.chapter,
            "chunk": i + 1,
            "fingerprint": version,
            "ingested_at": now,
        }))
        ids.append(record_id)
    return docs, ids, blank_pages
