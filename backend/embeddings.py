from langchain_huggingface import HuggingFaceEmbeddings

# Embedding 模型（构建时预下载，运行时直接用）
import os as _os, glob as _glob
_cache_base = "/app/.cache/huggingface"
_found = _glob.glob(f"{_cache_base}/models--BAAI--bge-small-zh-v1.5/snapshots/*", recursive=False)
if not _found:
    _found = _glob.glob(f"{_cache_base}/**/models--BAAI--bge-small-zh-v1.5/snapshots/*", recursive=True)
_model_path = _found[0] if _found else "BAAI/bge-small-zh-v1.5"
print(f"[EMBEDDING] Using model at: {_model_path}")
embeddings = HuggingFaceEmbeddings(
    model_name=_model_path,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
