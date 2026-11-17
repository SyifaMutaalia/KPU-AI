from app.services.ai_service import ABSTAIN, _is_nonfactual


def test_nonfactual_classifier_is_conservative():
    assert _is_nonfactual("Halo!")
    assert not _is_nonfactual("Halo, kapan jadwal pilkada?")
    assert "dokumen resmi" in ABSTAIN
