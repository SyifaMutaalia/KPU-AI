"""Offline, dependency-free unit tests for routing; no API requests."""
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def isolated_functions(path, names, globals_dict):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    module = ast.Module(body=fns, type_ignores=[])
    code = compile(ast.fix_missing_locations(module), str(path), "exec")
    exec(code, globals_dict)
    return globals_dict


@dataclass
class Source:
    title: str
    url: str


@dataclass
class AgentResult:
    answer: str
    sources: list
    grounded: bool


ai = isolated_functions(
    ROOT / "app/services/ai_service.py",
    {"_is_personal_dpt_question", "_asks_for_decision_text", "_personal_dpt_guidance"},
    {"re": re, "Source": Source, "AgentResult": AgentResult},
)
search = isolated_functions(
    ROOT / "app/rag/search.py", {"_exact_subang_decision_id"}, {"re": re},
)


class RoutingTests(unittest.TestCase):
    def test_dpt_question(self):
        self.assertTrue(ai["_is_personal_dpt_question"]("jika saya di jakarta maka dimana dpt saya?"))
        self.assertTrue(ai["_is_personal_dpt_question"]("Bagaimana cek TPS saya?"))
        self.assertFalse(ai["_is_personal_dpt_question"]("Apa ketentuan pembentukan PPK?"))

    def test_guidance_no_private_data(self):
        result = ai["_personal_dpt_guidance"]()
        self.assertEqual(result.sources[0].url, "https://cekdptonline.kpu.go.id/")
        self.assertIn("bukan di chat", result.answer)

    def test_exact_doc(self):
        question = "Apa yang diatur dalam Keputusan KPU Kabupaten Subang Nomor 4 Tahun 2024? Sertakan diktum dan halaman sumbernya."
        self.assertEqual(search["_exact_subang_decision_id"](question), "2024kpt4")
        self.assertTrue(ai["_asks_for_decision_text"](question))

    def test_dont_overmatch_pkpu(self):
        self.assertIsNone(search["_exact_subang_decision_id"]("Apa isi PKPU Nomor 4 Tahun 2024?"))
        self.assertIsNone(search["_exact_subang_decision_id"]("Apa isi Keputusan KPU RI Nomor 4 Tahun 2024?"))
        self.assertFalse(ai["_asks_for_decision_text"]("Apa perkembangan data pemilih terbaru di Subang?"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
