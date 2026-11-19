"""Pilot: PDF scan -> page-by-page Markdown via OpenAI Responses PDF input.

Run from repository root:
python -m scripts.llm_extract_pdf --pdf data/kpu_doc/kpu_jdih/2018kpt1264.pdf --start-page 3 --end-page 3 --confirm-send

No Tesseract, no Pinecone. Review every page against the original PDF.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from dotenv import dotenv_values
from pypdf import PdfReader, PdfWriter


EXTRACTION_PROMPT = """Anda adalah transkriptor dokumen hukum Indonesia, BUKAN peringkas.
Baca seluruh isi halaman PDF terlampir berdasarkan gambar halaman.
Kembalikan HANYA Markdown isi dokumen, dalam urutan baca yang benar.
- Pertahankan setiap kata, nomor, tanggal, Pasal, ayat, huruf, diktum (KESATU,
  KEDUA, dst), judul, catatan kaki, dan kepala/penutup halaman yang terlihat.
- Jangan menyimpulkan, menerjemahkan, mengoreksi, atau mengarang teks.
- Untuk teks kurang jelas tulis [TIDAK TERBACA] tepat pada bagiannya.
- Untuk tabel gunakan tabel Markdown dengan kolom dan relasi tiap baris yang
  benar; jangan menggabungkan dua baris atau mengarang nilai sel kosong.
- Jika tabel panjang, jangan menghilangkan baris, meski berulang.
- Label diktum di sisi kiri harus diikuti isi yang berpasangan di sisi kanan.
- Jangan menambahkan label Pasal/diktum jika tidak terlihat di halaman.
- Ini ekstraksi SATU HALAMAN, sehingga lanjutan Pasal/tabel mungkin ada di
  halaman berikutnya. Jangan menganggap unit hukum sudah lengkap.
"""


def one_page_bytes(reader: PdfReader, page_index: int) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    writer.write(output)
    return output.getvalue()


def extract_one(client, model: str, payload: bytes, filename: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    response = client.responses.create(
        model=model,
        store=False,
        instructions=EXTRACTION_PROMPT,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_file", "filename": filename,
                 "file_data": f"data:application/pdf;base64,{encoded}"},
                {"type": "input_text", "text": "Transkripsikan seluruh halaman ini secara lengkap ke Markdown."},
            ],
        }],
        max_output_tokens=12000,
    )
    if getattr(response, "status", None) == "incomplete":
        raise RuntimeError("Output LLM terpotong; halaman belum disimpan. Periksa max_output_tokens.")
    markdown = (response.output_text or "").strip()
    if not markdown:
        raise RuntimeError("LLM tidak menghasilkan Markdown; jangan lanjutkan chunking.")
    return markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF scan -> draft Markdown via LLM; no Pinecone")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--start-page", type=int, default=1, help="Halaman PDF, mulai dari 1")
    parser.add_argument("--end-page", type=int, default=None, help="Halaman PDF, inklusif")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--output-root", type=Path, default=Path("data/extracted_markdown"))
    parser.add_argument("--confirm-send", action="store_true", help="Izinkan PDF dikirim ke API eksternal")
    args = parser.parse_args()
    if not args.confirm_send:
        parser.error("Review data pribadi/izin dokumen dahulu, lalu tambahkan --confirm-send")
    if not args.pdf.is_file() or args.pdf.suffix.lower() != ".pdf":
        parser.error("--pdf harus menunjuk file PDF yang tersedia")
    config = dotenv_values(".env")
    key = config.get("OPENAI_API_KEY")
    if not key:
        parser.error("OPENAI_API_KEY tidak ada di .env backend")

    reader = PdfReader(args.pdf)
    start = args.start_page
    end = args.end_page if args.end_page is not None else start
    if not (1 <= start <= end <= len(reader.pages)):
        parser.error(f"Rentang halaman tidak valid, PDF punya {len(reader.pages)} halaman")

    out_dir = args.output_root / args.pdf.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=180, max_retries=1)
    source_sha = hashlib.sha256(args.pdf.read_bytes()).hexdigest()

    # Pilot outputs always describe their page range. Partial PDFs are NOT complete documents.
    pages = []
    for page_number in range(start, end + 1):
        print(f"Mengekstrak halaman {page_number}/{len(reader.pages)}: {args.pdf.name}")
        pdf_bytes = one_page_bytes(reader, page_number - 1)
        markdown = extract_one(client, args.model, pdf_bytes, f"page-{page_number:03d}.pdf")
        page_text = f"<!-- PAGE: {page_number} -->\n\n{markdown}\n"
        individual = out_dir / f"page-{page_number:03d}.draft.md"
        individual.write_text(page_text, encoding="utf-8")
        pages.append(page_text)
        print(f"  Disimpan: {individual}")

    range_name = f"pages-{start:03d}-{end:03d}"
    combined = out_dir / f"{range_name}.draft.md"
    combined.write_text("\n\n".join(pages), encoding="utf-8")
    metadata = {
        "source_pdf": args.pdf.as_posix(),
        "source_sha256": source_sha,
        "pages_extracted": list(range(start, end + 1)),
        "total_pdf_pages": len(reader.pages),
        "document_complete": start == 1 and end == len(reader.pages),
        "model": args.model,
        "review_status": "pending_manual_verification",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "combined_markdown": combined.as_posix(),
    }
    (out_dir / f"{range_name}.meta.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Draft gabungan: {combined}")
    print("PERIKSA PDF ASLI. Jika akurat, salin/koreksi ke file *.verified.md.")


if __name__ == "__main__":
    main()
