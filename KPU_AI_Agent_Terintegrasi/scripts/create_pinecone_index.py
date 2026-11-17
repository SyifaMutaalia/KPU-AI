
import os

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

INDEX_NAME = "kpu-subang-rag"
DIMENSION = 1536
METRIC = "cosine"

api_key = os.getenv("PINECONE_API_KEY")

if not api_key:
    raise RuntimeError(
        "PINECONE_API_KEY belum tersedia di .env"
    )

pc = Pinecone(api_key=api_key)

existing_indexes = pc.list_indexes().names()

if INDEX_NAME not in existing_indexes:
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric=METRIC,
        vector_type="dense",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        ),
    )
    print("Permintaan pembuatan index berhasil.")
else:
    print("Index sudah tersedia.")

# Validasi konfigurasi, jangan mengubah index lama.
index_info = pc.describe_index(INDEX_NAME)

if (
    index_info.dimension != DIMENSION
    or index_info.metric != METRIC
    or index_info.vector_type != "dense"
    or index_info.embed is not None
):
    raise RuntimeError(
        "Konfigurasi index tidak sesuai. "
        "Periksa index lama sebelum melanjutkan."
    )

print(f"Index: {index_info.name}")
print(f"Dimension: {index_info.dimension}")
print(f"Metric: {index_info.metric}")
print(f"Status: {index_info.status.state}")
