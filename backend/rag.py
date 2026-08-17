import os
import glob

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


# ========================= Embedding 模型 =========================
# 构建时预下载到容器内，运行时直接用本地缓存

_cache_base = "/app/.cache/huggingface"
_found = glob.glob(f"{_cache_base}/models--BAAI--bge-small-zh-v1.5/snapshots/*", recursive=False)
if not _found:
    _found = glob.glob(f"{_cache_base}/**/models--BAAI--bge-small-zh-v1.5/snapshots/*", recursive=True)
_model_path = _found[0] if _found else "BAAI/bge-small-zh-v1.5"
print(f"[EMBEDDING] Using model at: {_model_path}")

embeddings = HuggingFaceEmbeddings(
    model_name=_model_path,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)


# ========================= PDF 解析 & 索引 =========================

def ingest_rag_document(file_path):
    """解析 PDF → 分块 → 向量化 → 保存 FAISS 索引。"""
    DB_PATH = "faiss_db"
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(DB_PATH)


# ========================= 检索器 =========================

def get_retriever():
    """加载 FAISS 索引，返回相似度检索器（top-4）。"""
    DB_PATH = "faiss_db"
    vector_store = FAISS.load_local(
        folder_path=DB_PATH,
        embeddings=embeddings,
        allow_dangerous_deserialization=True
    )

    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4}
    )

    return retriever
