"""Offline tests; do not connect to OpenAI, Pinecone, or Neon."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class FakeSource:
    def __init__(self, title, url):
        self.title = title
        self.url = url

class Evidence:
    def __init__(self):
        self.sources = []
        self.review_refs = {}
        self.web_briefs = []
        self.retrieved = False
        self.web_searched = False
        self.used_draft_tool = False
        self.used_channels_tool = False

def load_service():
    modules = {
        'app': types.ModuleType('app'),
        'app.core': types.ModuleType('app.core'),
        'app.core.config': types.ModuleType('app.core.config'),
        'app.schemas': types.ModuleType('app.schemas'),
        'app.schemas.chat': types.ModuleType('app.schemas.chat'),
    }
    modules['app.core.config'].get_settings = lambda: None
    modules['app.schemas.chat'].Source = FakeSource
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location('isolated_kpu_ai_service', ROOT/'app/services/ai_service.py')
        m = importlib.util.module_from_spec(spec)
        sys.modules['isolated_kpu_ai_service'] = m
        spec.loader.exec_module(m)
    return m

service = load_service()

class CitationTests(unittest.TestCase):
    def setUp(self):
        self.e = Evidence()
        self.e.review_refs = {'D1': {'title':'2024kpt4', 'page_start':2, 'page_end':3, 'legal_reference':'KESATU', 'text':'Potongan keputusan.'}}

    def test_doc_valid_and_labeled_unverified(self):
        answer = service._finalize('Keputusan ini mengatur ... [D1]', self.e, 'Apa isi keputusan?')
        self.assertIn('BELUM DIVERIFIKASI', answer.answer)
        self.assertIn('[D1]', answer.answer)
        self.assertEqual(answer.sources, [])

    def test_invalid_doc_id_is_rejected(self):
        self.assertEqual(service._finalize('Kutipan [D9]', self.e, 'Apa isi?').answer, service.ABSTAIN)

    def test_web_valid_url(self):
        self.e.sources = [FakeSource('Website', 'https://www.kpu.go.id/abc')]
        answer = service._finalize('Keterangan terbaru [1]', self.e, 'Apa kabar terbaru?')
        self.assertTrue(answer.grounded)
        self.assertEqual(answer.sources[0].url, 'https://www.kpu.go.id/abc')

    def test_current_requires_official_web(self):
        answer = service._finalize('Isi keputusan historis [D1]', self.e, 'Aturan apa yang berlaku sekarang?')
        self.assertIn('belum menemukan rujukan web resmi', answer.answer)

    def test_end_to_end_no_citation_gets_repaired(self):
        # Agent omits the citation and even skips its tool; app retrieves
        # documentary evidence and asks the model to cite the exact result.
        self.e = Evidence()
        e = self.e
        s = types.SimpleNamespace(openai_api_key='test-key', openai_model='test-model', max_context_messages=8)
        class Msg:
            def __init__(self, content): self.content = content
        class Model:
            def __init__(self, **kwargs): pass
            def invoke(self, messages): return Msg('Keputusan tentang PAW PPK [D1]')
        class Tool:
            def invoke(self, args):
                e.retrieved = True
                e.review_refs['D1'] = {'title':'2024kpt4', 'page_start':1, 'page_end':2,
                                       'legal_reference':'KESATU', 'text':'Penggantian antarwaktu anggota PPK.'}
        class Web:
            def invoke(self, args): e.web_searched = True
        class Agent:
            def invoke(self, arg, config): return {'messages':[Msg('Jawaban tanpa sitasi')]}
        mod = {
            'langchain': types.ModuleType('langchain'),
            'langchain.agents': types.ModuleType('langchain.agents'),
            'langchain_core': types.ModuleType('langchain_core'),
            'langchain_core.messages': types.ModuleType('langchain_core.messages'),
            'langchain_openai': types.ModuleType('langchain_openai'),
            'app.agent': types.ModuleType('app.agent'),
            'app.agent.prompts': types.ModuleType('app.agent.prompts'),
            'app.agent.tools': types.ModuleType('app.agent.tools'),
        }
        mod['langchain.agents'].create_agent=lambda **kwargs:Agent()
        mod['langchain_core.messages'].HumanMessage=Msg
        mod['langchain_core.messages'].SystemMessage=Msg
        mod['langchain_core.messages'].AIMessage=Msg
        mod['langchain_openai'].ChatOpenAI=Model
        mod['app.agent.prompts'].SYSTEM_PROMPT='SYSTEM'
        mod['app.agent.tools'].Evidence=lambda:e
        mod['app.agent.tools'].build_tools=lambda evidence:[Tool(),Web()]
        with patch.dict(sys.modules, mod), patch.object(service,'get_settings',lambda:s):
            reply = service.answer_question('Apa isi Keputusan Nomor 4 Tahun 2024?', [])
        self.assertIn('Keputusan tentang PAW PPK', reply.answer)
        self.assertIn('[D1]', reply.answer)

    def test_repair_with_exact_citations(self):
        self.e.sources = []
        class Result:
            content = 'Diktum KESATU terdapat di halaman 2 [D1]'
        class FakeModel:
            def invoke(self, messages):
                self.messages = messages
                return Result()
        fake = FakeModel()
        class FakeMsg:
            def __init__(self, content):
                self.content = content
        lib = types.ModuleType('langchain_core')
        messages = types.ModuleType('langchain_core.messages')
        messages.SystemMessage = FakeMsg
        messages.HumanMessage = FakeMsg
        with patch.dict(sys.modules, {'langchain_core': lib, 'langchain_core.messages': messages}):
            answer = service._repair_from_evidence('Apa isi?', self.e, fake)
        self.assertIn('[D1]', answer)
        self.assertIn('Potongan keputusan.', fake.messages[0].content)

    def test_repair_uses_prior_user_questions_only_as_context(self):
        class Result:
            content = 'Diktum KESATU [D1]'
        class FakeModel:
            def invoke(self, messages):
                self.messages = messages
                return Result()
        fake = FakeModel()
        class FakeMsg:
            def __init__(self, content):
                self.content = content
        lib = types.ModuleType('langchain_core')
        messages = types.ModuleType('langchain_core.messages')
        messages.SystemMessage = FakeMsg
        messages.HumanMessage = FakeMsg
        history = [
            ('user', 'Apa isi Keputusan KPU Subang Nomor 4 Tahun 2024?'),
            ('assistant', 'UNVERIFIED_OLD_ASSISTANT_CLAIM'),
        ]
        with patch.dict(sys.modules, {'langchain_core': lib, 'langchain_core.messages': messages}):
            service._repair_from_evidence(
                'Apa bunyi diktum kesatu?', self.e, fake, history
            )
        prompt = fake.messages[1].content
        self.assertIn('Keputusan KPU Subang Nomor 4 Tahun 2024', prompt)
        self.assertIn('Apa bunyi diktum kesatu?', prompt)
        self.assertNotIn('UNVERIFIED_OLD_ASSISTANT_CLAIM', prompt)

if __name__ == '__main__':
    unittest.main()
