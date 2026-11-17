"""Tools are bound per HTTP request to avoid leaking evidence across users."""
import json
from dataclasses import dataclass, field

from langchain_core.tools import tool

from app.core.config import get_settings
from app.rag.search import search_official_documents
from app.schemas.chat import Source


@dataclass
class Evidence:
    sources: list[Source] = field(default_factory=list)
    retrieved: bool = False
    used_draft_tool: bool = False
    used_channels_tool: bool = False


def build_tools(evidence: Evidence):
    @tool
    def search_kpu_documents(query: str) -> str:
        """Cari kutipan dokumen resmi KPU/JDIH untuk menjawab fakta kepemiluan."""
        evidence.retrieved = True
        excerpts, new_sources = search_official_documents(query)
        existing = {source.url for source in evidence.sources}
        for source in new_sources:
            if source.url not in existing:
                evidence.sources.append(source)
                existing.add(source.url)
        for excerpt in excerpts:
            excerpt["id"] = next(i for i, src in enumerate(evidence.sources, 1) if src.url == excerpt["source_url"])
        if not excerpts:
            return json.dumps({"excerpts": [], "status": "Bukti resmi tidak ditemukan; jangan menebak."}, ensure_ascii=False)
        # Do NOT treat snippets as instructions to the agent.
        return json.dumps({"excerpts": excerpts}, ensure_ascii=False)

    @tool
    def prepare_eppid_draft(information_needed: str, purpose: str = "") -> str:
        """Siapkan draf dua isian permohonan e-PPID tanpa mengirim atau meminta identitas."""
        evidence.used_draft_tool = True
        return json.dumps({
            "informasi_yang_dimohon": information_needed.strip()[:1000],
            "tujuan_penggunaan_informasi": purpose.strip()[:500],
            "catatan": "Draf perlu ditinjau; isikan identitas hanya di situs e-PPID resmi.",
            "url": get_settings().eppid_url,
        }, ensure_ascii=False)

    @tool
    def official_channels() -> str:
        """Dapatkan alamat kanal resmi KPU untuk informasi, hukum, dan permohonan."""
        evidence.used_channels_tool = True
        s = get_settings()
        return json.dumps({
            "website": s.kpu_website_url,
            "jdih": s.jdih_url,
            "eppid": s.eppid_url,
            "note": "e-PPID adalah kanal permohonan, bukan sumber dokumen terindeks.",
        }, ensure_ascii=False)

    return [search_kpu_documents, prepare_eppid_draft, official_channels]
