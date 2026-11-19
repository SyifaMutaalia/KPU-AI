import unittest
from types import SimpleNamespace as NS

from app.agent.official_web import extract_web_citations, is_official_web_url


class OfficialWebTest(unittest.TestCase):
    def test_domains(self):
        self.assertTrue(is_official_web_url("https://kab-subang.kpu.go.id/a"))
        self.assertTrue(is_official_web_url("https://jdih.kpu.go.id/a"))
        self.assertTrue(is_official_web_url("https://www.kpu.go.id/a"))
        self.assertTrue(is_official_web_url("https://subang.go.id/a"))
        self.assertFalse(is_official_web_url("https://kab-tanahdatar.kpu.go.id/a"))
        self.assertFalse(is_official_web_url("https://kpu.go.id.evil.com/a"))
        self.assertFalse(is_official_web_url("http://kpu.go.id/a"))
        self.assertFalse(is_official_web_url("https://user:pw@kpu.go.id/a"))

    def test_only_approved_citations(self):
        anns = [
            NS(type="url_citation", url="https://jdih.kpu.go.id/abc", title="JDIH"),
            NS(type="url_citation", url="https://evil.example/abc", title="Evil"),
        ]
        response = NS(output=[NS(type="message", content=[NS(annotations=anns)])])
        sources = extract_web_citations(response)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].url, "https://jdih.kpu.go.id/abc")


if __name__ == "__main__":
    unittest.main()
