"""Structured draft generation; never sends anything to e-PPID."""
from pydantic import BaseModel, Field

from app.agent.prompts import DRAFT_SYSTEM_PROMPT
from app.core.config import get_settings
from app.schemas.eppid import DraftOut, DraftRequest


class DraftFields(BaseModel):
    informasi_yang_dimohon: str = Field(description="Rincian data/dokumen/informasi yang dimohon")
    tujuan_penggunaan_informasi: str = Field(description="Tujuan yang benar-benar disebutkan pemohon, atau kosong")


def generate_draft(request: DraftRequest) -> DraftOut:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    s = get_settings()
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY belum dikonfigurasi.")
    model = ChatOpenAI(model=s.openai_model, api_key=s.openai_api_key, use_responses_api=True, reasoning={"effort": "low"}, timeout=35, max_retries=1)
    response: DraftFields = model.with_structured_output(DraftFields).invoke([
        SystemMessage(content=DRAFT_SYSTEM_PROMPT),
        HumanMessage(content=f"Informasi yang dibutuhkan: {request.information_needed}\nTujuan yang diberikan: {request.purpose or '(belum disebutkan)'}"),
    ])
    # Fail closed on hallucinated purpose.
    return DraftOut(
        informasi_yang_dimohon=response.informasi_yang_dimohon.strip()[:1500],
        tujuan_penggunaan_informasi=response.tujuan_penggunaan_informasi.strip()[:750] if request.purpose else "",
        official_url=s.eppid_url,
        note="Periksa kecocokan dengan kolom pada formulir e-PPID KPU Subang sebelum menyalin. "
             "Identitas dan dokumen pendukung hanya diisi pada situs resmi; draf ini tidak dikirim otomatis.",
    )
