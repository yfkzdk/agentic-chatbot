"""Hybrid 检索（BM25 + 稠密向量 + RRF 融合 + 可选重排）。

移植自 ai-cookbook/knowledge/hybrid-retrieval 的四阶段检索栈：

    1. BM25      稀疏关键词检索 —— 命中精确词、符号、稀有术语
    2. Dense     稠密向量检索   —— 命中换词说法、语义相似
    3. RRF       倒数排名融合   —— 把两种排名合成一个（融合排名，不融合分数）
    4. Reranker  cross-encoder 重排 —— 在候选上做更精细的相关性打分（可选）

与同目录其他 RAG 管道的关系（三条管道并存，各有适用场景）：

    - rag.py 的 Semantic 管道：PDF → 分块 → FAISS 向量检索（rag_tool）
    - rag.py 的 Agentic 管道：grep 三件套（list_files / grep / read_file）
      精确符号、能跨文件追线索的知识库，实时读盘、不建索引
    - 本文件的 Hybrid 管道：对 corpus/ 文本做「关键词 + 向量」混合检索
      需要索引、又要兼顾精确词和换词说法的场景

    —— 三条管道的算法与实现均来自 ai-cookbook/knowledge/ 下
       agentic-rag（Agentic）与 hybrid-retrieval（本文件）两个目录。

相对原教程的关键适配（便于 review 时对照）：

    - 原教程用 bm25s 库        → 这里手写标准 Okapi BM25（零新依赖，
      算法一致；语料规模变大时换成 bm25s，search 接口不变即可）
    - 原教程用 OpenAI 向量模型  → 这里复用 rag.py 已加载的本地
      bge-small-zh-v1.5（无需 API key，与 Semantic 管道共用同一向量模型）
    - 原教程用 Cohere rerank API → 这里重排为可选阶段，未配置时优雅降级为
      「不重排，直接用 RRF 结果」
    - 原教程分块用 semantic-text-splitter → 这里沿用项目已有的
      RecursiveCharacterTextSplitter（约 512 token / 12% 重叠）
"""

import os
import math
import re

import jieba
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .rag import NOTES_DIR, embeddings


# ========================= 常量 =========================

BM25_K1 = 1.5          # BM25 词频饱和参数（标准值）
BM25_B = 0.75          # BM25 长度归一化参数（标准值）
RRF_K = 60             # RRF 平滑常数（2009 论文与教程的约定值）
CHUNK_SIZE = 512       # 分块大小（近似 token 数；原教程推荐 ~512 token）
CHUNK_OVERLAP = 64     # 分块重叠（~12%）
DEFAULT_K = 10         # 最终返回条数
CANDIDATE_K = 50       # 每个检索器先召回候选条数（供融合/重排）


# ========================= 分词 =========================

_CJK_RUN = re.compile(r"[a-zA-Z0-9_]+|[一-鿿]+")


def tokenize(text: str) -> list[str]:
    """把文本切成 BM25 的词元。

    中文用 jieba 分词（保证「连接池」「人工审批」这类词能整体命中）；
    英文/数字连续串按空白切分并统一小写。
    """
    tokens: list[str] = []
    for run in _CJK_RUN.findall(text.lower()):
        if run.isascii():
            tokens.append(run)
        else:
            tokens.extend(t for t in jieba.cut(run) if t.strip())
    return tokens


# ========================= 阶段 1：BM25 =========================

class BM25:
    """标准 Okapi BM25 关键词检索（纯 Python 实现）。

    打分公式（对查询中的每个词 t 累加）：
        idf(t) * f(t,d) * (k1+1) / (f(t,d) + k1*(1-b+b*|d|/avgdl))

    原教程用 bm25s 库（约 500x 更快、自带持久化）；这里手写公式是为了
    零依赖地呈现算法本身。语料规模大时替换成 bm25s，search 接口不变。
    """

    def __init__(self, k1: float = BM25_K1, b: float = BM25_B):
        self.k1 = k1
        self.b = b
        self._doc_freqs: list[dict[str, int]] = []  # 每篇文档的 {词: 词频}
        self._doc_len: list[int] = []               # 每篇文档长度（词数）
        self._idf: dict[str, float] = {}            # 词 → IDF
        self._avgdl: float = 0.0
        self._n_docs: int = 0

    def index(self, corpus: list[list[str]]) -> None:
        """用「每篇文档已经分词」的语料建索引。"""
        self._doc_freqs = []
        self._doc_len = []
        doc_freq: dict[str, int] = {}  # 词 → 出现该词的文档数

        for tokens in corpus:
            freq: dict[str, int] = {}
            for t in tokens:
                freq[t] = freq.get(t, 0) + 1
            self._doc_freqs.append(freq)
            self._doc_len.append(len(tokens))
            for t in set(tokens):
                doc_freq[t] = doc_freq.get(t, 0) + 1

        self._n_docs = len(corpus)
        self._avgdl = sum(self._doc_len) / max(1, self._n_docs)
        for t, n in doc_freq.items():
            # 标准 IDF 平滑：ln(1 + (N - n + 0.5) / (n + 0.5))
            self._idf[t] = math.log((self._n_docs - n + 0.5) / (n + 0.5) + 1)

    def search(self, query_tokens: list[str], k: int = DEFAULT_K) -> list[tuple[int, float]]:
        """返回 (文档下标, BM25 得分) 的 top-k 列表。"""
        scores = np.zeros(self._n_docs)
        for t in query_tokens:
            idf = self._idf.get(t)
            if idf is None:
                continue
            for i, freq in enumerate(self._doc_freqs):
                f = freq.get(t, 0)
                if f == 0:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self._doc_len[i] / self._avgdl)
                scores[i] += idf * f * (self.k1 + 1) / denom

        top = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]


# ========================= 阶段 2：Dense =========================

def _embed_texts(texts: list[str]) -> np.ndarray:
    """用项目共用的 bge 向量模型批量编码，返回 (N, dim) 的归一化矩阵。"""
    vecs = np.array(embeddings.embed_documents(texts), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 防止空向量除零
    return vecs / norms


def _embed_query(query: str) -> np.ndarray:
    """编码查询并归一化。"""
    vec = np.array(embeddings.embed_query(query), dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec if norm == 0 else vec / norm


# ========================= 阶段 3：RRF =========================

def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """把多个「doc_id 排名列表」融合成一个。

    关键点：融合的是「排名」，不是「分数」——BM25 分数无上界、余弦相似度
    落在 [0,1]，直接平均会失衡。RRF 用 1/(k+rank) 归一化后相加。

        rrf_score(d) = Σ_r 1 / (k + rank_r(d))
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


# ========================= 语料加载 & 分块 =========================

def load_corpus() -> list[tuple[str, str]]:
    """读取语料目录下所有 UTF-8 文本文件，返回 [(相对路径, 文本)]。

    doc_id 用相对路径保证稳定，BM25 与向量索引据此对齐。
    """
    docs: list[tuple[str, str]] = []
    for path in sorted(NOTES_DIR.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 跳过二进制或不可读文件
        if text.strip():
            docs.append((str(path.relative_to(NOTES_DIR)), text))
    return docs


def _chunk_documents(docs: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """把长文档切成带稳定 id 的块：chunk_id = "{doc_id}#{序号}"。

    分块原因（见 hybrid-retrieval/README）：单个文档超过向量模型输入上限
    或超过约 1000 token 时，单个向量无法有意义地概括全文，必须切块。
    原教程推荐 semantic-text-splitter，这里用项目已有的
    RecursiveCharacterTextSplitter 近似，按语料实测调 chunk_size/overlap。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunk_ids: list[str] = []
    chunk_texts: list[str] = []
    for doc_id, text in docs:
        for i, chunk in enumerate(splitter.split_text(text)):
            if chunk.strip():
                chunk_ids.append(f"{doc_id}#{i}")
                chunk_texts.append(chunk)
    return chunk_ids, chunk_texts


# ========================= 混合检索器 =========================

class HybridRetriever:
    """持有 BM25 索引 + 向量矩阵，提供混合检索。"""

    def __init__(self, chunk_ids: list[str], chunk_texts: list[str],
                 bm25: BM25, dense: np.ndarray):
        self.chunk_ids = chunk_ids
        self.chunk_texts = chunk_texts
        self.bm25 = bm25
        self.dense = dense  # (N, dim)，已归一化

    def get_text(self, chunk_id: str) -> str:
        """按 chunk_id 取回原文（调试/审计用）。"""
        idx = self.chunk_ids.index(chunk_id)
        return self.chunk_texts[idx]

    def _bm25_search(self, query: str, k: int) -> list[str]:
        return [self.chunk_ids[i] for i, _ in self.bm25.search(tokenize(query), k=k)]

    def _dense_search(self, query: str, k: int) -> list[str]:
        if self.dense.size == 0:
            return []
        sims = self.dense @ _embed_query(query)  # 归一化后点积即余弦相似度
        top = np.argsort(-sims)[:k]
        return [self.chunk_ids[i] for i in top if sims[i] > 0]

    def search(self, query: str, k: int = DEFAULT_K, candidate_k: int = CANDIDATE_K):
        """BM25 + dense 各召回 candidate_k 条 → RRF 融合 → 返回 top-k。

        返回 [(chunk_id, RRF 得分)]。
        """
        bm25_rank = self._bm25_search(query, candidate_k)
        dense_rank = self._dense_search(query, candidate_k)
        return reciprocal_rank_fusion([bm25_rank, dense_rank])[:k]


def build_hybrid_retriever() -> HybridRetriever:
    """对 corpus/ 文本建混合索引（BM25 + 向量），返回检索器。

    当前为进程内构建（不落盘）：语料每次启动重新编码。
    原教程把 BM25 索引和 embeddings.npy 持久化到磁盘；语料规模大、
    且希望避免每次重启重编码时，可仿照 2-bm25.py / 3-embed.py 加缓存。
    """
    docs = load_corpus()
    chunk_ids, chunk_texts = _chunk_documents(docs)

    if not chunk_texts:
        return HybridRetriever([], [], BM25(), np.zeros((0, 0)))

    tokenized = [tokenize(t) for t in chunk_texts]
    bm25 = BM25()
    bm25.index(tokenized)

    dense = _embed_texts(chunk_texts)
    return HybridRetriever(chunk_ids, chunk_texts, bm25, dense)


# ========================= 阶段 4：Rerank（可选） =========================

def rerank_with_cohere(query: str, candidate_ids: list[str],
                       corpus_by_id: dict[str, str], k: int = DEFAULT_K):
    """Cohere cross-encoder 重排（可选阶段）。

    移植自 hybrid-retrieval/utils/reranker.py。需要 `pip install cohere`
    且配置 COHERE_API_KEY。本地离线替代是 BAAI/bge-reranker-v2-m3。
    """
    import cohere  # 延迟导入，避免未安装时影响其余管道
    client = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))
    documents = [corpus_by_id[cid] for cid in candidate_ids]
    response = client.rerank(
        model="rerank-v4.0-fast",
        query=query,
        documents=documents,
        top_n=k,
    )
    return [(candidate_ids[r.index], r.relevance_score) for r in response.results]


def search_hybrid(query: str, retriever: HybridRetriever, k: int = DEFAULT_K,
                  candidate_k: int = CANDIDATE_K, rerank: bool = False):
    """混合检索入口：BM25 + dense → RRF →（可选）rerank。

    未开启 rerank，或 Cohere 未配置时，优雅降级为直接返回 RRF 结果。
    """
    fused = retriever.search(query, k=k, candidate_k=candidate_k)
    if not rerank:
        return fused

    try:
        by_id = dict(zip(retriever.chunk_ids, retriever.chunk_texts))
        return rerank_with_cohere(query, [cid for cid, _ in fused], by_id, k=k)
    except Exception as error:  # 缺 key / 缺库 / 网络失败都走这里
        print(f"[HYBRID] rerank 不可用，退回 RRF 结果：{error}")
        return fused


# ========================= 进程级单例 =========================

_retriever: HybridRetriever | None = None


def get_hybrid_retriever() -> HybridRetriever:
    """获取（首次构建并缓存）混合检索器。首次调用会对 corpus/ 建索引。"""
    global _retriever
    if _retriever is None:
        _retriever = build_hybrid_retriever()
    return _retriever
