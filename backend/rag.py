"""RAG 管道（本文件含 Semantic + Agentic 两条；Hybrid 在 hybrid.py）。

本后端共有三条 RAG 检索管道，算法分别来自 ai-cookbook/knowledge/ 下的
两个目录，各管一段适用场景：

    1. Semantic（本文件前半）—— PDF → 分块 → FAISS 向量检索（rag_tool 已接入）
       来源：项目原有实现；对应 hybrid-retrieval 里的 dense 思路
    2. Agentic（本文件后半）  —— grep 三件套 list_files / grep / read_file
       来源：ai-cookbook/knowledge/agentic-rag；精确符号、能追线索、不建索引
    3. Hybrid（hybrid.py）     —— BM25 + 向量 + RRF 融合 + 可选 rerank
       来源：ai-cookbook/knowledge/hybrid-retrieval；关键词与语义兼顾

三者互补：Semantic/Hybrid 靠索引，Agentic 靠实时 grep。
"""

import os
import glob
import re
from pathlib import Path

from pydantic import BaseModel, Field

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


# ========================= 结构化答案（Agentic RAG 输出） =========================
# 移植自 ai-cookbook/knowledge/agentic-rag：让最终回答带引用，
# 下游代码（API/前端）可以直接信任结构，而不是去解析自由文本。

class Citation(BaseModel):
    """答案中某条论断所依赖的一条出处。"""

    file: str = Field(description="语料目录下的相对文件路径")
    quote: str = Field(description="文件中支持该论断的原文行")
    line_number: int = Field(description="原文行的行号")


class SearchAnswer(BaseModel):
    """带引用的结构化答案。"""

    answer: str = Field(description="用自然语言给出的答案")
    citations: list[Citation] = Field(description="支撑答案的文件与原文行")


# ========================= Agentic 检索 =========================
# 移植自 ai-cookbook/knowledge/agentic-rag 的生产级三工具接口：
#   list_files —— 发现：看语料目录里有哪些文件
#   grep       —— 缩小：按正则逐行搜出候选匹配
#   read_file  —— 取证：读取被选中的具体文件（按行范围有界读取）
#
# 与上面 Semantic RAG 的区别：
#   Semantic（rag_tool）靠向量相似度一次性召回 top-k 片段；
#   Agentic（这三个工具）让模型自己循环「发现→缩小→取证」，
#   并把安全约束（路径沙箱、行数上限、数量上限）固化在工具实现里。

# 语料目录：默认取 backend/ 下的 corpus/，可用环境变量 RAG_CORPUS_DIR 覆盖。
# 与 AI Cookbook 的 notes/ 目录一一对应：把要检索的 .md/.txt 等文本放进这里即可。
NOTES_DIR = Path(os.getenv("RAG_CORPUS_DIR", str(Path(__file__).parent / "corpus"))).resolve()

READ_MAX_LINES = 200
GREP_MAX_RESULTS = 30


def _safe_path(path: str):
    """把模型给出的路径解析到语料目录内，越界则返回 None（路径沙箱）。"""
    try:
        target = (NOTES_DIR / path).resolve()
    except (OSError, ValueError):
        return None
    if not target.is_relative_to(NOTES_DIR):
        return None
    return target


def list_files(pattern: str = "*.md") -> str:
    """列出语料目录下匹配 glob 模式的文件（相对路径）。"""
    if not NOTES_DIR.exists():
        return f"Error: corpus directory not found at {NOTES_DIR}"

    try:
        matches = sorted(
            str(p.relative_to(NOTES_DIR))
            for p in NOTES_DIR.glob(pattern)
            if p.is_file() and p.is_relative_to(NOTES_DIR)
        )
    except (NotImplementedError, ValueError) as error:
        return f"Error: invalid glob pattern {pattern!r}: {error}"

    if not matches:
        return f"No files matched pattern: {pattern}"
    return "\n".join(matches)


def grep(pattern: str, max_results: int = GREP_MAX_RESULTS, context: int = 0) -> str:
    """逐行搜索语料目录下所有文本文件，返回 `file:line: text` 匹配行。

    匹配不分大小写，按正则解释。`context` 可携带每个命中前后的行数。
    工具始终返回可读字符串，出错时返回 `Error: ...` 而不是抛异常，
    这样模型能从坏正则或缺失文件中自行恢复。
    """
    if max_results < 1:
        return "Error: max_results must be 1 or greater."
    if context < 0:
        return "Error: context must be 0 or greater."

    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as error:
        return f"Error: invalid pattern {pattern!r}: {error}"

    hits: list[str] = []
    for file in sorted(NOTES_DIR.rglob("*")):
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 跳过二进制或不可读文件
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if not rx.search(line):
                continue
            rel = file.relative_to(NOTES_DIR)
            start = max(1, i - context)
            end = min(len(lines), i + context)
            for j in range(start, end + 1):
                hits.append(f"{rel}:{j}: {lines[j - 1].strip()}")
            if len(hits) >= max_results:
                hits = hits[:max_results]
                hits.append(
                    f"... truncated to {max_results} matches. Try a more specific pattern."
                )
                return "\n".join(hits)

    if not hits:
        return f"No matches found for pattern: {pattern}"
    return "\n".join(hits)


def read_file(path: str, offset: int = 1, limit: int = READ_MAX_LINES) -> str:
    """按行范围读取语料目录下的一个文件（默认最多 200 行）。

    模型给出相对路径，Python 负责校验是否越界，越界/缺失/非文本都返回可读错误。
    """
    safe = _safe_path(path)
    if safe is None:
        return f"Error: path {path!r} is outside the corpus directory."
    if not safe.exists():
        return f"Error: file not found: {path}"
    if not safe.is_file():
        return f"Error: {path} is not a file."
    if offset < 1:
        return "Error: offset must be 1 or greater."
    if limit < 1:
        return "Error: limit must be 1 or greater."
    if limit > READ_MAX_LINES:
        return f"Error: limit must be {READ_MAX_LINES} lines or fewer."

    try:
        lines = safe.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"Error: {path} is not UTF-8 text."

    end = min(offset + limit - 1, len(lines))
    excerpt = lines[offset - 1:end]
    if not excerpt:
        return f"No lines found. {path} has {len(lines)} lines."
    return "\n".join(f"{i}: {line}" for i, line in enumerate(excerpt, start=offset))
