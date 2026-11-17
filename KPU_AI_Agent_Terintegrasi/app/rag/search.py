from app.core.config import get_settings
from app.core.safety import is_approved_source
from app.rag.store import get_vectorstore
from app.schemas.chat import Source


def search_official_documents(query: str) -> tuple[list[dict], list[Source]]:
    settings = get_settings()
    if not settings.rag_enabled:
        return [], []
    # Only retrieve documents explicitly reviewed as currently effective.
    # Legacy vectors without legal_status metadata are intentionally excluded.
    results = get_vectorstore().similarity_search_with_score(
        query, k=settings.rag_top_k, filter={"legal_status": {"$eq": "berlaku"}}
    )
    excerpts: list[dict] = []
    sources: list[Source] = []
    seen: set[str] = set()
    for document, score in results:
        if score is None or float(score) < settings.rag_min_score:
            continue
        url = str(document.metadata.get("source_url") or "")
        if not is_approved_source(url, settings.rag_allowed_hosts):
            continue
        title = str(document.metadata.get("title") or "Dokumen resmi KPU")[:160]
        content = document.page_content.strip()
        if not content:
            continue
        excerpts.append({"id": len(excerpts) + 1, "title": title, "source_url": url, "text": content[:1500], "similarity_score": round(float(score), 3)})
        if url not in seen:
            sources.append(Source(title=title, url=url))
            seen.add(url)
    return excerpts, sources
