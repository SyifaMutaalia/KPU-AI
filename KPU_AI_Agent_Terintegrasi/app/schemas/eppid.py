from pydantic import BaseModel, Field


class DraftRequest(BaseModel):
    information_needed: str = Field(min_length=10, max_length=1000)
    purpose: str = Field(default="", max_length=500)


class DraftOut(BaseModel):
    informasi_yang_dimohon: str
    tujuan_penggunaan_informasi: str
    official_url: str
    note: str
