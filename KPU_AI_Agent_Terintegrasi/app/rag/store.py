"""Pinecone connection and retrieval. The Pinecone index must exist already.

Dimension must match the configured embedding model: text-embedding-3-small -> 1536.
"""
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from app.core.config import get_settings


@lru_cache
def get_vectorstore() -> PineconeVectorStore:
    settings = get_settings()
    if not (settings.openai_api_key and settings.pinecone_api_key and settings.pinecone_index_name):
        raise RuntimeError("OpenAI/Pinecone belum dikonfigurasi. Isi .env terlebih dahulu.")
    embeddings = OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
    )
    return PineconeVectorStore(
        index_name=settings.pinecone_index_name,
        embedding=embeddings,
        pinecone_api_key=settings.pinecone_api_key,
        namespace=settings.pinecone_namespace,
    )
