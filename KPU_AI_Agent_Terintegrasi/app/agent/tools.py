"""Tools LangChain request-local: Pinecone, web resmi, e-PPID, kanal resmi."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from langchain_core.tools import tool

from app.agent.official_web import search_official_web
from app.core.config import get_settings
from app.rag.search import search_official_documents
from app.schemas.chat import Source

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    sources: list[Source] = field(default_factory=list)
    source_evidence: dict[int, list[str]] = field(default_factory=dict)
    # Referensi internal belum memiliki URL resmi; jangan kirim sebagai URL palsu.
    review_refs: dict[str, dict] = field(default_factory=dict)
    web_briefs: list[str] = field(default_factory=list)
    retrieved: bool = False
    web_searched: bool = False
    web_queries: list[str] = field(default_factory=list)
    used_draft_tool: bool = False
    used_channels_tool: bool = False


def build_tools(evidence: Evidence):
    def get_or_add_source(
        title: str, url: str, kind: str = "web", note: str | None = None
    ) -> int:
        for i, item in enumerate(evidence.sources, 1):
            if item.url == url:
                if kind == "dokumen":
                    item.kind = "dokumen"
                    item.note = item.note or note
                return i
        evidence.sources.append(Source(title=title, url=url, kind=kind, note=note))
        return len(evidence.sources)

    @tool
    def search_kpu_documents(query: str) -> str:
        """Cari potongan dokumen kepemiluan di Pinecone; kembalikan halaman dan status hukum."""
        evidence.retrieved = True
        try:
            excerpts, _ = search_official_documents(query)
        except Exception as exc:
            logger.warning("Pinecone retrieval gagal: %s", type(exc).__name__)
            return json.dumps(
                {"status": "pencarian_dokumen_gagal", "excerpts": []},
                ensure_ascii=False,
            )
        for excerpt in excerpts:
            url = excerpt.get("source_url") or ""
            if url:
                unverified = excerpt.get("legal_status") != "berlaku"
                idx = get_or_add_source(
                    excerpt["title"],
                    url,
                    kind="dokumen",
                    note="Status keberlakuan belum diverifikasi" if unverified else None,
                )
                excerpt["id"] = idx
                evidence.source_evidence.setdefault(idx, []).append(
                    "\n".join(
                        part
                        for part in (
                            f"Jenis dokumen: {excerpt.get('document_type') or ''}",
                            f"Nomor/tahun: {excerpt.get('document_number') or ''}/{excerpt.get('year') or ''}",
                            f"Bagian: {excerpt.get('legal_reference') or ''}",
                            f"Status hukum: {excerpt.get('legal_status') or 'belum_diverifikasi'}",
                            f"Kutipan: {excerpt.get('text') or ''}",
                        )
                        if part.strip()
                    )[:3500]
                )
            else:
                # Nomor D1, D2... menunjukkan dokumen INTERNAL, bukan tautan resmi.
                key = (
                    excerpt.get("document_id"),
                    excerpt.get("page_start"),
                    excerpt.get("page_end"),
                    excerpt.get("legal_reference"),
                )
                existing = next(
                    (
                        ref
                        for ref, info in evidence.review_refs.items()
                        if info["key"] == key
                    ),
                    None,
                )
                if existing is None:
                    existing = f"D{len(evidence.review_refs) + 1}"
                    evidence.review_refs[existing] = {
                        "key": key,
                        "title": excerpt["title"],
                        "text": excerpt.get("text", ""),
                        "legal_reference": excerpt.get("legal_reference", ""),
                        "page_start": excerpt.get("page_start"),
                        "page_end": excerpt.get("page_end"),
                        "legal_status": excerpt.get(
                            "legal_status", "belum_diverifikasi"
                        ),
                    }
                excerpt["id"] = existing
        if not excerpts:
            return json.dumps(
                {"status": "tidak_ditemukan", "excerpts": []}, ensure_ascii=False
            )
        return json.dumps(
            {"status": "ditemukan", "excerpts": excerpts}, ensure_ascii=False
        )

    @tool
    def search_web_resmi(query: str) -> str:
        """Cari berita, jadwal, peraturan terbaru hanya di situs resmi KPU RI/KPU Subang dan Pemkab Subang."""
        evidence.web_searched = True
        evidence.web_queries.append(query)
        logger.info("Web search query: %s", query[:200])
        try:
            summary, results = search_official_web(query)
        except Exception as exc:
            logger.warning("Web search gagal: %s", type(exc).__name__)
            return json.dumps(
                {"status": "pencarian_web_gagal", "sources": []}, ensure_ascii=False
            )
        mapped = []
        for source in results:
            idx = get_or_add_source(source.title, source.url)
            mapped.append({"id": idx, "title": source.title, "url": source.url})
        if mapped:
            evidence.web_briefs.append(summary[:4500])
            for item in mapped:
                evidence.source_evidence.setdefault(item["id"], []).append(
                    f"Ringkasan dari pencarian resmi: {summary[:3500]}"
                )
        return json.dumps(
            {
                "status": "ditemukan" if mapped else "tidak_ditemukan",
                "ringkasan": summary
                if mapped
                else "Tidak ada sumber web resmi yang berhasil disitasi.",
                "sources": mapped,
            },
            ensure_ascii=False,
        )

    @tool
    def prepare_eppid_draft(information_needed: str, purpose: str = "") -> str:
        """Siapkan draf permohonan e-PPID untuk disalin; tidak mengirim atau meminta identitas."""
        evidence.used_draft_tool = True
        return json.dumps(
            {
                "informasi_yang_dimohon": information_needed.strip()[:1000],
                "tujuan_penggunaan_informasi": purpose.strip()[:500],
                "catatan": "Draf perlu ditinjau; isikan identitas hanya di situs e-PPID resmi.",
                "url": get_settings().eppid_url,
            },
            ensure_ascii=False,
        )

    @tool
    def official_channels() -> str:
        """Daftar layanan resmi KPU RI, KPU Kabupaten Subang, dan Pemkab Subang (cek DPT, info calon,
        hasil pemilu/pilkada, JDIH, PPID/e-PPID, berita). Gunakan untuk mengarahkan warga ke layanan yang tepat."""
        from app.agent.official_services import catalog

        evidence.used_channels_tool = True
        return json.dumps(
            {"layanan": catalog(),
             "note": "Arahkan warga ke layanan yang sesuai. e-PPID adalah kanal permohonan, bukan sumber dokumen terindeks."},
            ensure_ascii=False,
        )

    @tool
    def read_official_page(url: str) -> str:
        """Baca isi satu halaman di situs resmi (kpu.go.id, kab-subang.kpu.go.id, jdih.kpu.go.id, subang.go.id,
        peraturan.bpk.go.id). Pakai untuk membuka halaman yang ditemukan search_web_resmi atau disebut pengguna,
        bila ringkasan pencarian belum cukup rinci."""
        from app.agent.official_web import fetch_official_page

        evidence.web_searched = True
        try:
            title, text, clean_url = fetch_official_page(url)
        except Exception as exc:
            logger.warning("Baca halaman resmi gagal: %s", type(exc).__name__)
            return json.dumps({"status": "gagal_dibuka", "url": url[:300]}, ensure_ascii=False)
        idx = get_or_add_source(title, clean_url)
        evidence.source_evidence.setdefault(idx, []).append(text[:3500])
        return json.dumps({"status": "ditemukan", "id": idx, "title": title, "url": clean_url, "isi": text[:6000]},
                          ensure_ascii=False)

    return [
        search_kpu_documents,
        search_web_resmi,
        prepare_eppid_draft,
        official_channels,
        read_official_page,
    ]
