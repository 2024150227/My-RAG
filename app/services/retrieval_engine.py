# 检索引擎
import re
from app.services.chroma_service import chroma_service
from app.services.embedding_service import embedding_service
from app.services.rerank_service import rerank_service
from app.services.llm_service import llm_service
from app.utils.timer import time_block
from app.config import settings
from app.utils.logger import logger

# Query 改写 prompt——把口语化/含糊的用户 query 转成对检索友好的专业表述
QUERY_REWRITE_PROMPT = """你是一个检索优化助手。用户输入的查询可能口语化、不完整或含歧义。
请将其改写成对向量检索更友好的专业表述，要求：
1. 保留原查询的所有关键信息，不凭空添加
2. 使用与知识库文档一致的专业术语
3. 保持简洁，直接输出改写结果，不要解释

原始查询：{query}
改写结果："""


class RetrievalEngine:
    def __init__(self):
        self.top_k = settings.TOP_K

    def _rewrite_query(self, query: str) -> str:
        """对用户原始 query 做改写，缩小语义鸿沟，提升向量检索的召回率。

        改写失败（LLM 不可用 / 超时等）时静默回退到原 query，
        不影响主链路。
        """
        try:
            prompt = QUERY_REWRITE_PROMPT.format(query=query)
            rewritten = llm_service.generate(prompt)
            if rewritten and rewritten.strip() and "LLM调用失败" not in rewritten:
                rewritten = rewritten.strip()
                logger.info(f"query 改写: '{query[:40]}' → '{rewritten[:80]}'")
                return rewritten
        except Exception as e:
            logger.warning(f"query 改写失败，回退原始 query: {e}")
        return query

    def bm25_search(self, query: str, documents: list, top_n: int = 5) -> list:
        results = []
        for idx, doc in enumerate(documents):
            score = self._bm25_score(query, doc)
            if score > 0:
                results.append({'document': doc, 'score': score, 'index': idx})

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]

    def _bm25_score(self, query: str, document: str) -> float:
        query_terms = set(query.lower().split())
        doc_terms = document.lower().split()

        if not query_terms:
            return 0.0

        score = 0.0
        for term in query_terms:
            if term in doc_terms:
                score += 1.0

        return score / len(query_terms)

    def hybrid_search(self, query: str, user_id: str = None) -> list:
        """混合检索（改写 → 向量 + BM25 → 重排）。

        返回 list[dict]，每项含：
            document         - chunk 文本
            relevance_score  - rerank 分数
            metadata         - 原 chunk 的 metadata（含 filename / images 等）

        各阶段耗时通过 ``time_block`` 写入 rag_hooks.execution_stats[sid]["node_timings"]，
        前提是上层（hooks_manager.before_agent）已经 set_session 绑定上下文。
        """
        # 0. Query 改写：缩小语义鸿沟，改写后的 query 走向量检索，原 query 走 BM25
        with time_block("query_rewrite"):
            query_enhanced = self._rewrite_query(query)

        # 1. query 向量化（用改写后的 query）
        with time_block("query_embedding"):
            query_embedding = embedding_service.get_embedding(query_enhanced)
        if not query_embedding:
            return []

        # 2. 向量检索（暴力 KNN，文档少时精度优先）
        where = {"user_id": user_id} if user_id else None
        with time_block("vector_search"):
            vector_results = chroma_service.knn_search(
                query_embedding, n_results=self.top_k * 2, where=where
            )

        if not vector_results:
            return []

        # document → metadata 映射，rerank 之后回填用
        doc_to_meta = {res['document']: res.get('metadata') or {} for res in vector_results}
        documents = [res['document'] for res in vector_results]

        # 3. BM25 检索（用原 query，保留关键词匹配能力）
        with time_block("bm25_search"):
            bm25_results = self.bm25_search(query, documents, top_n=self.top_k * 2)
        bm25_docs = [res['document'] for res in bm25_results]

        # 4. 合并 + 去重
        with time_block("merge_dedup"):
            combined_docs = list(set(documents + bm25_docs))

        if len(combined_docs) == 0:
            return []

        # 5. 重排（用改写后的 query，语义更清晰）
        with time_block("rerank"):
            reranked = rerank_service.rerank(query_enhanced, combined_docs, top_n=self.top_k)

        return [{
            'document': item['document'],
            'relevance_score': item['relevance_score'],
            'metadata': doc_to_meta.get(item['document'], {}),
        } for item in reranked]

retrieval_engine = RetrievalEngine()
