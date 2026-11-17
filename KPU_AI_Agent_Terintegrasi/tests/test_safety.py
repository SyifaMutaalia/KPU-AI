from app.core.safety import contains_sensitive_identifiers, is_approved_source


def test_reject_sensitive_identifiers():
    assert contains_sensitive_identifiers("NIK 1234567890123456")
    assert contains_sensitive_identifiers("kontak saya@contoh.id")
    assert contains_sensitive_identifiers("telepon 081234567890")
    assert not contains_sensitive_identifiers("Bagaimana mencari dokumen Pemilu 2024?")


def test_source_allowlist_blocks_subdomain_and_url_tricks():
    hosts = ["jdih.kpu.go.id", "kab-subang.kpu.go.id"]
    assert is_approved_source("https://jdih.kpu.go.id/berkas/123.pdf", hosts)
    assert not is_approved_source("http://jdih.kpu.go.id/", hosts)
    assert not is_approved_source("https://jdih.kpu.go.id.evil.org/test", hosts)
    assert not is_approved_source("https://jdih.kpu.go.id@evil.org/test", hosts)
    assert not is_approved_source("https://evil.org", hosts)
    assert not is_approved_source("https://jdih.kpu.go.id:444/test", hosts)
