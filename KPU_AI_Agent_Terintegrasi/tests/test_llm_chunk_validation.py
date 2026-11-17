"""Offline tests for zero-loss chunk reconstruction; no API key needed."""
import unittest

from scripts.llm_chunk_markdown import BoundaryPlan, LegalBoundary, build_preview, verify_boundaries


class TestBoundaryValidation(unittest.TestCase):
    def make_chunk(self, start: int, end: int) -> LegalBoundary:
        return LegalBoundary(start_line=start, end_line=end, unit_type="diktum",
                             legal_reference="KESATU", needs_review=False, review_note="")

    def test_exact_reconstruction_and_pages(self):
        src = "<!-- PAGE: 3 -->\n### KESATU\nTeks satu.\n### KEDUA\nTeks dua.\n"
        plan = BoundaryPlan(chunks=[self.make_chunk(1, 3), self.make_chunk(4, 5)])
        preview = build_preview(src, "sample.verified.md", plan, "test-model")
        self.assertEqual("".join(c["text_md"] for c in preview["chunks"]), src)
        self.assertEqual(preview["chunks"][0]["pages"], [3])
        self.assertFalse(preview["pinecone_uploaded"])

    def test_reject_gap(self):
        plan = BoundaryPlan(chunks=[self.make_chunk(1, 2), self.make_chunk(4, 4)])
        with self.assertRaises(ValueError):
            verify_boundaries(plan, 4)

    def test_reject_overlap(self):
        plan = BoundaryPlan(chunks=[self.make_chunk(1, 3), self.make_chunk(3, 4)])
        with self.assertRaises(ValueError):
            verify_boundaries(plan, 4)


if __name__ == "__main__":
    unittest.main()
