"""Pencarian RAG produksi atau index review lokal untuk AI Agent yang sama.

Tidak ada bypass AI Agent. Namespace review hanya boleh digunakan dalam development;
vektor dengan legal_status=belum_diverifikasi tidak pernah dipromosikan otomatis.
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from app.core.config import get_settings
from app.core.safety import is_approved_source
from app.rag.store import get_vectorstore
from app.schemas.chat import Source

logger = logging.getLogger(__name__)
REVIEW_NAMESPACE = "kpu_review_2024_2026"
PRODUCTION_LEGAL_STATUSES = ("berlaku", "belum_diverifikasi")
_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "apa",
    "apakah",
    "bagaimana",
    "dalam",
    "dan",
    "dari",
    "di",
    "dengan",
    "itu",
    "jelaskan",
    "kah",
    "ke",
    "kepada",
    "untuk",
    "yang",
    "tentang",
}


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in _WORD.findall(query.lower())
        if len(term) > 2 and term not in _STOP_WORDS
    }


def _explicit_regulation_reference(query: str) -> tuple[str, str] | None:
    match = re.search(
        r"\b(?:nomor|no\.?)\s*(\d{1,5})\s*tahun\s*(20\d{2})\b",
        query.lower(),
    )
    return match.groups() if match else None


def _document_reference_matches(query: str, metadata: dict) -> bool:
    requested = _explicit_regulation_reference(query)
    if not requested:
        return True
    number, year = requested
    actual_number = str(metadata.get("document_number") or "").strip()
    actual_year = str(metadata.get("year") or "").strip()
    if not actual_number or not actual_year:
        return False
    if actual_number.lstrip("0") != number.lstrip("0") or actual_year != year:
        return False
    identity = " ".join(
        (
            str(metadata.get("document_type") or ""),
            str(metadata.get("title") or ""),
        )
    ).lower()
    lowered_query = query.lower()
    if re.search(r"\bpkpu\b", lowered_query) and "pkpu" not in identity:
        return False
    if "keputusan" in lowered_query and "keputusan" not in identity:
        return False
    return True


def _foreign_locality(query: str, title: str, settings) -> bool:
    host = urlsplit(settings.kpu_website_url).hostname or ""
    tenant_match = re.search(r"\b(?:kab|kota)[-.]([^.]+)", host.lower())
    tenant = tenant_match.group(1).replace("-", " ") if tenant_match else ""
    if not tenant:
        return False
    locality_match = re.search(
        r"\b(?:kab(?:upaten)?|kota)\s*[-.:]?\s*"
        r"([a-z]+(?:[\s-]+[a-z]+){0,2}?)"
        r"(?=\s+(?:nomor|no\.?|tahun|tentang|perihal)\b|[,;:]|$)",
        title.lower(),
    )
    if not locality_match:
        return False
    locality = locality_match.group(1).replace("-", " ").strip()
    return locality != tenant and locality not in query.lower()


def _relevant_result(
    query: str, metadata: dict, content: str, score: float, settings
) -> bool:
    title = str(metadata.get("title") or "").strip()
    document_type = str(metadata.get("document_type") or "").strip()
    if not title or not document_type:
        return False
    if _foreign_locality(query, title, settings):
        return False
    if not _document_reference_matches(query, metadata):
        return False
    query_terms = _query_terms(query)
    document_terms = _query_terms(
        " ".join(
            (
                title,
                document_type,
                str(metadata.get("document_number") or ""),
                str(metadata.get("year") or ""),
                content,
            )
        )
    )
    stronger_score = max(settings.rag_min_score + 0.15, 0.75)
    return len(query_terms & document_terms) >= 2 or score >= stronger_score


def current_rag_mode(settings=None) -> str:
    """Mode review hanya tersedia ketika APP_ENV=development dan flag eksplisit."""
    s = settings or get_settings()
    requested = os.getenv("KPU_RAG_SOURCE", "production").strip().lower()
    if requested == "review":
        if s.app_env != "development":
            raise RuntimeError(
                "KPU_RAG_SOURCE=review hanya diperbolehkan dalam development"
            )
        return "review"
    return "production"


def _exact_subang_decision_id(query: str) -> str | None:
    """Only infer an ID when the user explicitly names a Subang KPU decision.

    A mention of PKPU Number 4, or merely "number 4", is insufficient.
    """
    lower = query.lower()
    if not re.search(r"\bkeputusan\b", lower):
        return None
    if not re.search(r"\b(kpu|komisi pemilihan umum)\b", lower):
        return None
    if not re.search(r"\bsubang\b", lower):
        return None
    match = re.search(r"\bnomor\s*(\d{1,5})\s*tahun\s*(20\d{2})\b", lower)
    if not match:
        return None
    number, year = match.groups()
    return f"{year}kpt{int(number)}"


def search_official_documents(query: str) -> tuple[list[dict], list[Source]]:
    s = get_settings()
    mode = current_rag_mode(s)
    if mode == "review":
        if not (s.openai_api_key and s.pinecone_api_key and s.pinecone_index_name):
            raise RuntimeError("OpenAI/Pinecone belum dikonfigurasi di backend")
        store = PineconeVectorStore(
            index_name=s.pinecone_index_name,
            embedding=OpenAIEmbeddings(
                api_key=s.openai_api_key, model=s.openai_embedding_model
            ),
            pinecone_api_key=s.pinecone_api_key,
            namespace=REVIEW_NAMESPACE,
        )
        filter_expression = {
            "chunk_review_status": {"$eq": "manually_reviewed_for_staging"}
        }
        exact_id = _exact_subang_decision_id(query)
        if exact_id:
            filter_expression = {
                "$and": [filter_expression, {"document_id": {"$eq": exact_id}}]
            }
            logger.info("RAG exact document filter=%s", exact_id)
    else:
        if not getattr(s, "rag_enabled", True):
            return [], []
        store = get_vectorstore()
        # Dokumen yang dicabut/tidak berlaku tidak pernah dipakai sebagai bukti.
        # "belum_diverifikasi" = status di JDIH tidak terbaca saat ingestion;
        # jawaban akan diberi catatan agar pengguna memeriksa tautan sumber.
        filter_expression = {"legal_status": {"$in": list(PRODUCTION_LEGAL_STATUSES)}}

    namespace = REVIEW_NAMESPACE if mode == "review" else s.pinecone_namespace
    k = (
        max(s.rag_top_k, 12)
        if mode == "review" and _exact_subang_decision_id(query)
        else s.rag_top_k
    )
    results = store.similarity_search_with_score(query, k=k, filter=filter_expression)
    excerpts: list[dict] = []
    sources: list[Source] = []
    seen_urls: set[str] = set()
    for doc, score in results:
        if score is None or float(score) < s.rag_min_score:
            continue
        md = doc.metadata
        metadata_namespace = str(md.get("namespace") or "").strip()
        if metadata_namespace and metadata_namespace != namespace:
            continue
        url = str(md.get("source_url") or "").strip()
        official_url = url if is_approved_source(url, s.rag_allowed_hosts) else ""
        if (url and not official_url) or (mode == "production" and not official_url):
            continue
        content = doc.page_content.strip()
        score = float(score)
        if not content or not _relevant_result(query, md, content, score, s):
            continue
        title = str(md["title"]).strip()[:160]
        excerpt = {
            "title": title,
            "document_id": str(md.get("document_id") or ""),
            "document_type": str(md.get("document_type") or ""),
            "document_number": str(md.get("document_number") or ""),
            "year": md.get("year"),
            "legal_reference": str(md.get("legal_reference") or ""),
            "page_start": md.get("page_start"),
            "page_end": md.get("page_end"),
            "legal_status": str(md.get("legal_status") or "belum_diverifikasi"),
            "source_url": official_url,
            "text": content[:3500],
            "similarity_score": round(score, 4),
        }
        excerpts.append(excerpt)
        if official_url and official_url not in seen_urls:
            seen_urls.add(official_url)
            sources.append(Source(title=title, url=official_url, kind="dokumen"))
    logger.info(
        "RAG mode=%s namespace=%s results=%s query_chars=%s",
        mode,
        namespace,
        len(excerpts),
        len(query),
    )
    return excerpts, sources
