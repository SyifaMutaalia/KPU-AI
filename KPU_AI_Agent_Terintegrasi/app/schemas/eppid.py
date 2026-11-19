from pydantic import BaseModel, Field


class DraftRequest(BaseModel):
    information_needed: str = Field(min_length=10, max_length=1000)
    purpose: str = Field(default="", max_length=500)


class DraftOut(BaseModel):
    """Isian formulir permohonan e-PPID KPU Kabupaten Subang, urut sesuai formulirnya.

    Kolom identitas (nama, NIK, alamat, kontak) sengaja tidak ada: pemohon
    mengisinya sendiri di situs e-PPID resmi.
    """

    informasi_yang_dimohon: str
    tujuan_penggunaan_informasi: str
    official_url: str
    note: str
    jenis_pemohon: str = "Perorangan"
    cara_memperoleh_informasi: str = "Mendapat Salinan Informasi Softcopy"
    cara_memperoleh_salinan: str = "Email"
    format_salinan: str = "Terkirim"
    form_url: str = ""
