"""Agent menyusun isian formulir permohonan e-PPID; tidak pernah mengirim apa pun ke e-PPID."""
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.prompts import DRAFT_SYSTEM_PROMPT
from app.core.config import get_settings
from app.schemas.eppid import DraftOut, DraftRequest

JENIS_PEMOHON = ("Perorangan", "Kelompok Orang", "Badan Hukum")
CARA_MEMPEROLEH_INFORMASI = (
    "Melihat / Membaca / Mendengarkan / Mencatat",
    "Mendapat Salinan Informasi Hardcopy",
    "Mendapat Salinan Informasi Softcopy",
)
CARA_MEMPEROLEH_SALINAN = ("Mengambil Langsung", "Email", "Kurir/POS", "Faksimili")
FORMAT_SALINAN = ("Tercetak", "Terkirim")


class DraftFields(BaseModel):
    rincian_informasi: str = Field(
        description="Kolom 'Rincian Informasi Yang Dibutuhkan': kalimat permohonan formal dan spesifik "
        "(jenis data/dokumen, periode, wilayah, tingkat rincian) yang disusun dari kebutuhan pemohon"
    )
    tujuan_penggunaan: str = Field(
        description="Kolom 'Tujuan Penggunaan Informasi': kalimat formal dari tujuan yang disebutkan pemohon; "
        "string kosong bila pemohon tidak menyebut tujuan"
    )
    jenis_pemohon: Literal["Perorangan", "Kelompok Orang", "Badan Hukum"] = Field(
        description="Perorangan kecuali pemohon jelas menyebut kelompok atau lembaga berbadan hukum"
    )
    cara_memperoleh_informasi: Literal[
        "Melihat / Membaca / Mendengarkan / Mencatat",
        "Mendapat Salinan Informasi Hardcopy",
        "Mendapat Salinan Informasi Softcopy",
    ] = Field(description="Default: Mendapat Salinan Informasi Softcopy, kecuali pemohon menyebut lain")
    cara_memperoleh_salinan: Literal["Mengambil Langsung", "Email", "Kurir/POS", "Faksimili"] = Field(
        description="Default: Email, kecuali pemohon menyebut lain"
    )
    format_salinan: Literal["Tercetak", "Terkirim"] = Field(
        description="Terkirim untuk softcopy/email; Tercetak untuk hardcopy atau diambil langsung"
    )


def generate_draft(request: DraftRequest) -> DraftOut:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    s = get_settings()
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY belum dikonfigurasi.")
    model = ChatOpenAI(
        model=s.openai_model,
        api_key=s.openai_api_key,
        use_responses_api=True,
        reasoning={"effort": "low"},
        timeout=35,
        max_retries=1,
    )
    response: DraftFields = model.with_structured_output(DraftFields).invoke([
        SystemMessage(content=DRAFT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"Data yang dibutuhkan: {request.information_needed}\n"
            f"Untuk apa: {request.purpose or '(belum disebutkan)'}"
        ),
    ])
    base = s.eppid_url.rstrip("/")
    return DraftOut(
        informasi_yang_dimohon=response.rincian_informasi.strip()[:1500],
        # Tidak boleh mengarang tujuan: kosong bila pemohon tidak menyebutnya.
        tujuan_penggunaan_informasi=response.tujuan_penggunaan.strip()[:750] if request.purpose.strip() else "",
        jenis_pemohon=response.jenis_pemohon,
        cara_memperoleh_informasi=response.cara_memperoleh_informasi,
        cara_memperoleh_salinan=response.cara_memperoleh_salinan,
        format_salinan=response.format_salinan,
        official_url=s.eppid_url,
        form_url=f"{base}/formulir-permohonan",
        note="Login di e-PPID, lalu isi identitas Anda sendiri (nama, nomor identitas, kontak, alamat) "
             "langsung di formulir resmi. Periksa kembali isian sebelum menekan Simpan; draf ini tidak dikirim otomatis.",
    )
