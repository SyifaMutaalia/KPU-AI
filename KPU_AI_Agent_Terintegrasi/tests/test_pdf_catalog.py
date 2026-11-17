"""Offline validation tests; intentionally don't need OpenAI, Pinecone or LangChain."""
from dataclasses import replace
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.rag.pdf_catalog import read_catalog, pdf_pages
from app.rag.pdf_chunks import fingerprint


@pytest.fixture
def inventory(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    pdf = root / "peraturan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with pdf.open("wb") as stream:
        writer.write(stream)
    catalog = tmp_path / "catalog.csv"
    return root, pdf, catalog


def write_catalog(path, *, file_path="peraturan.pdf", status="berlaku", source_url="https://jdih.kpu.go.id/"):
    import csv
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file_path", "document_type", "document_number", "year", "title", "source_url", "legal_status", "issued_date"])
        writer.writeheader()
        writer.writerow({"file_path":file_path, "document_type":"pkpu", "document_number":"1", "year":2024,
                         "title":"Contoh judul yang hanya dipakai dalam pengujian", "source_url":source_url,
                         "legal_status":status, "issued_date":"2024-01-01"})


def test_read_valid_manifest(inventory):
    root, pdf, manifest = inventory
    write_catalog(manifest)
    entry = read_catalog(manifest, root, ["jdih.kpu.go.id"])[0]
    assert entry.document_type == "pkpu"
    assert entry.legal_status == "berlaku"
    assert entry.file_path == pdf
    assert len(entry.document_id) == 32


def test_reject_untrusted_host(inventory):
    root, _, manifest = inventory
    write_catalog(manifest, source_url="https://jdih.kpu.go.id.malicious.test/")
    with pytest.raises(ValueError, match="URL bukan host"):
        read_catalog(manifest, root, ["jdih.kpu.go.id"])


def test_reject_pdf_outside_root(inventory, tmp_path):
    root, _, manifest = inventory
    write_catalog(manifest, file_path="../foreign.pdf")
    (tmp_path / "foreign.pdf").write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="path harus PDF"):
        read_catalog(manifest, root, ["jdih.kpu.go.id"])


def test_reject_unknown_status(inventory):
    root, _, manifest = inventory
    write_catalog(manifest, status="valid sampai kapanpun")
    with pytest.raises(ValueError, match="status harus"):
        read_catalog(manifest, root, ["jdih.kpu.go.id"])


def test_fingerprint_changes_with_reviewed_metadata(inventory):
    root, _, manifest = inventory
    write_catalog(manifest)
    entry = read_catalog(manifest, root, ["jdih.kpu.go.id"])[0]
    assert fingerprint(entry) != fingerprint(replace(entry, legal_status="dicabut"))


def test_blank_page_is_reported(inventory):
    root, _, manifest = inventory
    write_catalog(manifest)
    entry = read_catalog(manifest, root, ["jdih.kpu.go.id"])[0]
    assert list(pdf_pages(entry)) == [(1, "")]


def test_langchain_chunk_payload_and_ids(inventory, monkeypatch):
    """Fake LangChain classes permit testing extraction orchestration offline."""
    import sys
    import types
    from app.rag import pdf_chunks
    root, _, manifest = inventory
    write_catalog(manifest)
    entry = read_catalog(manifest, root, ["jdih.kpu.go.id"])[0]
    class FakeDocument:
        def __init__(self, page_content, metadata):
            self.page_content, self.metadata = page_content, metadata
    class FakeSplitter:
        def __init__(self, **kwargs):
            self.options = kwargs
        def split_text(self, text):
            return [text[:40], text[40:]] if len(text) > 40 else [text]
    monkeypatch.setitem(sys.modules, "langchain_core", types.ModuleType("langchain_core"))
    lc_documents = types.ModuleType("langchain_core.documents")
    lc_documents.Document = FakeDocument
    monkeypatch.setitem(sys.modules, "langchain_core.documents", lc_documents)
    splitters = types.ModuleType("langchain_text_splitters")
    splitters.RecursiveCharacterTextSplitter = FakeSplitter
    monkeypatch.setitem(sys.modules, "langchain_text_splitters", splitters)
    monkeypatch.setattr(pdf_chunks, "pdf_pages", lambda e: iter([(1, "a" * 100), (2, "")]))
    documents, ids, blank_pages = pdf_chunks.build_chunks(entry, "0123456789abcdef", chunk_size=500, chunk_overlap=60)
    assert len(documents) == len(ids) == 2
    assert blank_pages == 1
    assert all(d.metadata["source_url"] == entry.source_url and d.metadata["page"] == 1 for d in documents)
    assert all(d.metadata["legal_status"] == "berlaku" for d in documents)
    assert len(set(ids)) == 2
    assert ids[0].startswith("kpu-")


def test_create_manifest_requires_review_and_no_overwrite(tmp_path):
    from scripts.create_manifest import create_manifest
    root = tmp_path / "docs"
    (root / "pkpu").mkdir(parents=True)
    (root / "keputusan_kpu_subang").mkdir()
    (root / "pkpu" / "sample.pdf").write_bytes(b"%PDF-test")
    (root / "keputusan_kpu_subang" / "sample.pdf").write_bytes(b"%PDF-test")
    manifest = tmp_path / "inventory.csv"
    assert create_manifest(root, manifest) == {"keputusan_kpu_subang":1, "pkpu":1}
    content = manifest.read_text(encoding="utf-8-sig")
    assert "belum_diverifikasi" in content
    assert "https://" not in content
    with pytest.raises(FileExistsError):
        create_manifest(root, manifest)
