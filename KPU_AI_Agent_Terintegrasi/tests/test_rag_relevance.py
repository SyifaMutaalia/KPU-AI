from types import SimpleNamespace

from app.rag import search


class FakeDocument:
    def __init__(self, content, metadata):
        self.page_content = content
        self.metadata = metadata


class FakeStore:
    def __init__(self, results):
        self.results = results

    def similarity_search_with_score(self, query, *, k, filter):
        return self.results


def test_retrieval_rejects_foreign_or_weak_documents_and_keeps_relevant_source(
    monkeypatch,
):
    settings = SimpleNamespace(
        rag_enabled=True,
        rag_top_k=5,
        rag_min_score=0.55,
        rag_allowed_hosts=["jdih.kpu.go.id", "kab-subang.kpu.go.id"],
        app_env="production",
        kpu_website_url="https://kab-subang.kpu.go.id/",
        pinecone_namespace="kpu-subang",
    )
    results = [
        (
            FakeDocument(
                "Informasi daftar pemilih tetap dan pemungutan suara.",
                {
                    "title": "KPU KAB-TANAH DATAR",
                    "document_type": "Keputusan",
                    "document_number": "1",
                    "year": 2024,
                    "source_url": "https://jdih.kpu.go.id/foreign",
                    "legal_status": "berlaku",
                },
            ),
            0.91,
        ),
        (
            FakeDocument(
                "Data pemilih lama tersedia pada arsip administrasi.",
                {
                    "title": "Pedoman Administrasi",
                    "document_type": "Pedoman",
                    "document_number": "2",
                    "year": 2024,
                    "source_url": "https://jdih.kpu.go.id/unrelated",
                    "legal_status": "berlaku",
                },
            ),
            0.61,
        ),
        (
            FakeDocument(
                "Daftar Pemilih Tetap (DPT) memuat pemilih yang telah memenuhi syarat.",
                {
                    "title": "Ketentuan DPT KPU Kabupaten Subang",
                    "document_type": "PKPU",
                    "document_number": "1",
                    "year": 2024,
                    "source_url": "https://jdih.kpu.go.id/subang",
                    "legal_status": "berlaku",
                },
            ),
            0.68,
        ),
        (
            FakeDocument(
                "Daftar Pemilih Tetap (DPT) memuat pemilih yang telah memenuhi syarat.",
                {
                    "title": "Salinan DPT dari namespace lain",
                    "document_type": "PKPU",
                    "document_number": "1",
                    "year": 2024,
                    "source_url": "https://jdih.kpu.go.id/other-namespace",
                    "legal_status": "berlaku",
                    "namespace": "unconfigured-namespace",
                },
            ),
            0.92,
        ),
    ]
    monkeypatch.setattr(search, "get_settings", lambda: settings)
    monkeypatch.setattr(search, "current_rag_mode", lambda _settings: "production")
    monkeypatch.setattr(search, "get_vectorstore", lambda: FakeStore(results))

    excerpts, sources = search.search_official_documents(
        "Apa ketentuan DPT untuk pemilih di Subang?"
    )

    assert [item["title"] for item in excerpts] == [
        "Ketentuan DPT KPU Kabupaten Subang"
    ]
    assert [item.url for item in sources] == ["https://jdih.kpu.go.id/subang"]


def test_explicit_regulation_number_and_type_must_match_document_metadata():
    query = "Apa isi PKPU Nomor 1 Tahun 2024?"

    assert (
        search._relevant_result(
            query,
            {
                "title": "PKPU Nomor 2 Tahun 2024",
                "document_type": "pkpu",
                "document_number": "2",
                "year": 2024,
            },
            "PKPU Nomor 2 Tahun 2024",
            0.95,
            SimpleNamespace(
                rag_min_score=0.55,
                kpu_website_url="https://kab-subang.kpu.go.id/",
            ),
        )
        is False
    )


def test_retrieval_does_not_create_document_titles_or_citations_from_missing_metadata(
    monkeypatch,
):
    settings = SimpleNamespace(
        rag_enabled=True,
        rag_top_k=5,
        rag_min_score=0.55,
        rag_allowed_hosts=["jdih.kpu.go.id"],
        app_env="production",
        kpu_website_url="https://kab-subang.kpu.go.id/",
        pinecone_namespace="kpu-subang",
    )
    store = FakeStore(
        [
            (
                FakeDocument(
                    "Ketentuan pemilih pada pemilihan umum.",
                    {
                        "document_id": "unknown-document-id",
                        "source_url": "https://jdih.kpu.go.id/unknown",
                        "legal_status": "berlaku",
                    },
                ),
                0.9,
            )
        ]
    )
    monkeypatch.setattr(search, "get_settings", lambda: settings)
    monkeypatch.setattr(search, "current_rag_mode", lambda _settings: "production")
    monkeypatch.setattr(search, "get_vectorstore", lambda: store)

    excerpts, sources = search.search_official_documents(
        "Apa ketentuan pemilih pada pemilihan umum?"
    )

    assert excerpts == []
    assert sources == []
