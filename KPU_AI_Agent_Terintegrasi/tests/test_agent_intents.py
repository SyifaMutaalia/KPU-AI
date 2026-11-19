import pytest

from app.core.config import Settings
from app.services import ai_service


def test_pinecone_rag_is_enabled_by_default():
    settings = Settings(session_secret="s" * 40, _env_file=None)

    assert settings.rag_enabled is True


def test_google_comparison_is_identity_intent_without_ai_or_retrieval(monkeypatch):
    def unexpected_settings_access():
        pytest.fail("Identity questions must not initialize the RAG/LLM path")

    monkeypatch.setattr(ai_service, "get_settings", unexpected_settings_access)

    result = ai_service.answer_question("Apa bedanya kamu dengan Google?", [])

    assert result.sources == []
    assert result.grounded is False
    assert "KPU Kabupaten Subang" in result.answer
    assert "Google" in result.answer


def test_election_regulation_is_routed_to_election_information():
    assert ai_service.classify_intent("Apa isi PKPU Nomor 1 Tahun 2024?") == "election"


def test_out_of_scope_question_does_not_initialize_ai_or_retrieval(monkeypatch):
    def unexpected_settings_access():
        pytest.fail("Out-of-scope questions must not initialize the RAG/LLM path")

    monkeypatch.setattr(ai_service, "get_settings", unexpected_settings_access)

    result = ai_service.answer_question("Bagaimana cara membuat roti?", [])

    assert result.sources == []
    assert result.grounded is False
    assert "informasi kepemiluan" in result.answer.lower()


def test_nasi_goreng_recipe_is_rejected_without_sources_or_ai(monkeypatch):
    def unexpected_settings_access():
        pytest.fail("Recipe questions must not initialize the RAG/LLM path")

    monkeypatch.setattr(ai_service, "get_settings", unexpected_settings_access)

    result = ai_service.answer_question("resep nasi goreng", [])

    assert result.sources == []
    assert result.grounded is False
    assert "di luar cakupan" in result.answer
    assert "jdih" not in result.answer.lower()


def test_bare_tahapan_question_asks_for_election_context_without_ai(monkeypatch):
    def unexpected_settings_access():
        pytest.fail("An underspecified timeline must ask for clarification")

    monkeypatch.setattr(ai_service, "get_settings", unexpected_settings_access)

    result = ai_service.answer_question("tahapan", [])

    assert ai_service.classify_intent("tahapan") == "election"
    assert result.sources == []
    assert "Pemilu atau Pilkada" in result.answer


def test_undated_election_timeline_requires_current_web_search():
    assert ai_service._is_current_question("tahapan pemilu")
    assert not ai_service._is_current_question("tahapan pemilu tahun 2024")
    assert ai_service.classify_intent("jadwal restoran") == "out_of_scope"


def test_election_terms_take_precedence_over_general_similarity():
    assert ai_service.classify_intent("Apa bedanya PPK dengan PPS?") == "election"
