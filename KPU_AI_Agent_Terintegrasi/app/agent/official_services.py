"""Katalog layanan resmi KPU RI, KPU Kabupaten Subang, dan Pemkab Subang.

Dipakai agent (tool official_channels) dan ditambahkan otomatis sebagai tautan
"Layanan resmi" di bawah jawaban bila pertanyaan menyinggung layanan tersebut.
Hanya alamat resmi berdomain kpu.go.id / subang.go.id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.chat import Source


@dataclass(frozen=True)
class Service:
    name: str
    url: str
    description: str
    keywords: tuple[str, ...]


SERVICES: tuple[Service, ...] = (
    Service("Cek DPT Online (KPU RI)", "https://cekdptonline.kpu.go.id/",
            "Cek apakah Anda terdaftar sebagai pemilih dan lokasi TPS dengan NIK.",
            (r"cek dpt", r"terdaftar", r"daftar pemilih", r"\bdpt\b", r"lokasi tps", r"tps saya", r"\bnik\b")),
    Service("Info Pemilu (KPU RI)", "https://infopemilu.kpu.go.id/",
            "Profil peserta pemilu: partai politik, daftar calon, dan daerah pemilihan.",
            (r"\bcalon\b", r"\bcaleg\b", r"profil", r"partai", r"parpol", r"peserta pemilu", r"dapil", r"daerah pemilihan", r"\bdct\b", r"\bdcs\b")),
    Service("Hasil Pemilu 2024 (KPU RI)", "https://pemilu2024.kpu.go.id/",
            "Publikasi hasil penghitungan suara Pemilu 2024 (Sirekap).",
            (r"hasil pemilu", r"hasil suara", r"perolehan suara", r"sirekap", r"rekapitulasi", r"hasil pilpres", r"hasil pileg", r"quick count", r"hitung")),
    Service("Hasil Pilkada 2024 (KPU RI)", "https://pilkada2024.kpu.go.id/",
            "Publikasi hasil penghitungan suara Pilkada Serentak 2024.",
            (r"hasil pilkada", r"hasil pilbup", r"hasil pilgub", r"perolehan suara pilkada")),
    Service("JDIH KPU", "https://jdih.kpu.go.id/",
            "Basis data peraturan dan keputusan KPU (PKPU, Keputusan KPU, keputusan daerah).",
            (r"pkpu", r"peraturan kpu", r"keputusan kpu", r"regulasi", r"\bjdih\b", r"dasar hukum")),
    Service("PPID KPU RI", "https://ppid.kpu.go.id/",
            "Layanan permohonan informasi publik tingkat KPU RI.",
            (r"\bppid\b", r"informasi publik", r"permohonan informasi")),
    Service("e-PPID KPU Kabupaten Subang", "https://subangkabppid.kpu.go.id/",
            "Ajukan permohonan informasi publik ke KPU Kabupaten Subang.",
            (r"e-?ppid", r"permohonan informasi", r"minta data", r"meminta data", r"informasi publik")),
    Service("KPU Kabupaten Subang", "https://kab-subang.kpu.go.id/",
            "Berita, pengumuman, dan informasi kepemiluan KPU Kabupaten Subang.",
            (r"kpu subang", r"kpu kabupaten subang", r"pengumuman", r"rekrutmen", r"\bpps\b", r"\bppk\b", r"\bkpps\b", r"ad ?hoc")),
    Service("Berita KPU RI", "https://www.kpu.go.id/berita",
            "Berita dan siaran pers terbaru dari KPU RI.",
            (r"berita", r"terbaru", r"siaran pers")),
    Service("JDIH Pemerintah Kabupaten Subang", "https://jdih.subang.go.id/",
            "Peraturan daerah dan peraturan bupati Subang, termasuk aturan Pilkades secara elektronik (e-voting).",
            (r"e-?voting", r"evoting", r"pemungutan suara (?:digital|elektronik)", r"pilkades digital",
             r"pemilihan (?:digital|elektronik)", r"peraturan bupati", r"\bperbup\b", r"\bperda\b")),
    Service("Pemerintah Kabupaten Subang", "https://subang.go.id/",
            "Portal resmi Pemkab Subang, termasuk informasi Pilkades.",
            (r"pilkades", r"kepala desa", r"pemkab", r"pemerintah kabupaten subang", r"\bdpmd\b")),
)


def match_services(question: str, limit: int = 3) -> list[Source]:
    """Layanan resmi yang relevan dengan pertanyaan, urut menurut banyaknya kata kunci yang cocok."""
    text = question.lower()
    scored = []
    for order, service in enumerate(SERVICES):
        hits = sum(1 for pattern in service.keywords if re.search(pattern, text))
        if hits:
            scored.append((-hits, order, service))
    return [
        Source(title=service.name, url=service.url, kind="layanan", note=service.description)
        for _, _, service in sorted(scored)[:limit]
    ]


def catalog() -> list[dict[str, str]]:
    return [{"nama": s.name, "url": s.url, "fungsi": s.description} for s in SERVICES]
