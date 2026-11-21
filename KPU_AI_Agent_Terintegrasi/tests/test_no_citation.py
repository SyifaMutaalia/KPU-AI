"""Bukti perilaku: pertanyaan kepemiluan yang tidak punya sitasi valid tidak dijawab dengan karangan."""
from unittest.mock import patch

from app.agent.official_services import match_services
from app.services import ai_service as service


class Evidence:
    def __init__(self):
        self.sources = []
        self.review_refs = {}
        self.web_briefs = []
        self.retrieved = True
        self.web_searched = True
        self.used_draft_tool = False
        self.used_channels_tool = False


QUESTION = "Berapa jumlah TPS di Desa Cibogo untuk Pemilu 2029?"


def test_answer_without_citation_becomes_abstain():
    # Model menulis angka tanpa rujukan: ditolak, bukan ditampilkan.
    result = service._finalize("Jumlah TPS di Desa Cibogo adalah 12 TPS.", Evidence(), QUESTION)
    assert result.answer == service.ABSTAIN
    assert result.grounded is False
    assert result.sources == []


def test_citation_to_unknown_source_becomes_abstain():
    # Nomor sitasi yang tidak ada di bukti juga ditolak.
    result = service._finalize("Ada 12 TPS [3].", Evidence(), QUESTION)
    assert result.answer == service.ABSTAIN


def test_abstain_still_points_user_to_official_services():
    abstain = service.AgentResult(answer=service.ABSTAIN, sources=[], grounded=False)
    with patch.object(service, "_answer_core", return_value=abstain):
        result = service.answer_question("Di mana lokasi TPS saya? Saya mau cek DPT", [])
    assert result.answer == service.ABSTAIN
    assert result.grounded is False
    urls = [source.url for source in result.sources]
    assert "https://cekdptonline.kpu.go.id/" in urls
    assert all(source.kind == "layanan" for source in result.sources)


def test_out_of_scope_answer_gets_no_service_links():
    refusal = service.AgentResult(answer=service.OUT_OF_SCOPE_ANSWER, sources=[], grounded=False)
    with patch.object(service, "_answer_core", return_value=refusal):
        result = service.answer_question("resep nasi goreng dong", [])
    assert result.sources == []


def test_match_services_pilkades_points_to_pemkab():
    assert [s.url for s in match_services("jadwal pilkades subang 2026")] == ["https://subang.go.id/"]
