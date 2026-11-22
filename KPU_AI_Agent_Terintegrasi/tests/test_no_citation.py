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


def test_event_specific_question_without_year_asks_which_election():
    result = service._answer_core("Siapa ketua KPPS TPS 05 Desa Pagaden?", [])
    assert "tahun berapa" in result.answer
    assert result.sources == []


def test_future_election_data_is_not_available_yet():
    result = service._answer_core("Siapa ketua KPPS TPS 05 Desa Pagaden pada Pemilu 2029?", [])
    assert "2029 belum dilaksanakan" in result.answer


def test_year_check_does_not_block_general_questions():
    for question in ("Apa syarat menjadi anggota KPPS?", "Bagaimana cara cek DPT saya?",
                     "Berapa jumlah pemilih Kabupaten Subang terbaru?"):
        assert not service._needs_election_year(question), question
    assert service._future_year("Kapan jadwal Pemilu 2029?") is None


def test_follow_up_with_year_in_history_is_not_asked_again():
    history = [("user", "Siapa ketua KPPS TPS 05 Desa Pagaden?"), ("assistant", "tahun berapa?"),
               ("user", "Pilkada 2024")]
    assert service._year_in_recent_history(history)


def test_e_voting_is_election_topic_and_points_to_subang_jdih():
    assert service._ELECTION_TERMS.search("bagaimana cara pemungutan suara digital pilkades?")
    assert service._ELECTION_TERMS.search("apa itu e-voting")
    urls = [s.url for s in match_services("bagaimana cara e-voting pilkades subang")]
    assert "https://jdih.subang.go.id/" in urls


def test_answer_keeps_both_document_and_web_sources_when_both_cited():
    from app.schemas.chat import Source
    evidence = Evidence()
    evidence.sources = [
        Source(title="PKPU 1/2025", url="https://jdih.kpu.go.id/data/data_pkpu/2025pkpu001.pdf", kind="dokumen"),
        Source(title="Berita KPU", url="https://www.kpu.go.id/berita/baca/1", kind="web"),
        Source(title="Tidak dipakai", url="https://www.kpu.go.id/berita/baca/2", kind="web"),
    ]
    result = service._finalize("Syarat pemilih adalah WNI berusia 17 tahun [1][2].", evidence, "Apa syarat menjadi pemilih?")
    assert [s.kind for s in result.sources] == ["dokumen", "web"]
    assert "Tidak dipakai" not in [s.title for s in result.sources]


def test_tidy_answer_drops_status_berlaku_but_keeps_tidak_berlaku():
    text = ("Syarat pemilih adalah WNI berusia 17 tahun [1].\n"
            "Status hukum sumber peraturan: berlaku. [1][2]\n"
            "Ketentuan ada di PKPU 1/2025 Pasal 4; status hukum keduanya berlaku.\n"
            "PKPU lama berstatus hukum tidak berlaku.")
    tidy = service._tidy_answer(text)
    assert "Status hukum sumber" not in tidy
    assert "keduanya berlaku" not in tidy
    assert "Pasal 4." in tidy
    assert "tidak berlaku" in tidy
    assert tidy.startswith("Syarat pemilih adalah WNI berusia 17 tahun [1].")
