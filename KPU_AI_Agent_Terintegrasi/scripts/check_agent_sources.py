"""Pemeriksaan retrieval agent yang sesungguhnya, tanpa mengubah database."""
from app.rag.search import current_rag_mode, search_official_documents

print("MODE:", current_rag_mode())
question = "Apa isi Keputusan KPU Kabupaten Subang Nomor 4 Tahun 2024?"
excerpts, sources = search_official_documents(question)
print("CHUNKS:", len(excerpts))
for item in excerpts[:5]:
    print(
        "DOKUMEN:", item["document_id"],
        "BAGIAN:", item["legal_reference"],
        "HALAMAN:", item["page_start"], "-", item["page_end"],
        "SKOR:", item["similarity_score"],
        "STATUS:", item["legal_status"],
    )
print("TAUTAN RESMI:", len(sources))
