# 检索引擎
import re
from app.services.chroma_service import chroma_service
from app.services.embedding_service import embedding_service
from app.services.rerank_service import rerank_service
from app.config import settings

class RetrievalEngine:
    def __init__(self):
        self.top_k = settings.TOP_K

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
        """混合检索（向量 + BM25 → 重排）。

        返回 list[dict]，每项含：
            document         - chunk 文本
            relevance_score  - rerank 分数
            metadata         - 原 chunk 的 metadata（含 filename / images 等）
        """
        query_embedding = embedding_service.get_embedding(query)
        if not query_embedding:
            return []

        # user_id 不为空时按用户过滤；为空时不过滤（兼容老调用 / 系统级查询）
        where = {"user_id": user_id} if user_id else None
        vector_results = chroma_service.query(query_embedding, n_results=self.top_k * 2, where=where)

        if not vector_results:
            return []

        # document → metadata 映射，rerank 之后回填用
        # 同一 chunk 文本理论上只对应一份 metadata；BM25 也是从 vector_results 中再筛，
        # 不会引入新文本，因此这一份映射对 combined_docs 完全够覆盖
        doc_to_meta = {res['document']: res.get('metadata') or {} for res in vector_results}

        documents = [res['document'] for res in vector_results]

        bm25_results = self.bm25_search(query, documents, top_n=self.top_k * 2)
        bm25_docs = [res['document'] for res in bm25_results]

        combined_docs = list(set(documents + bm25_docs))

        if len(combined_docs) == 0:
            return []

        reranked = rerank_service.rerank(query, combined_docs, top_n=self.top_k)

        return [{
            'document': item['document'],
            'relevance_score': item['relevance_score'],
            'metadata': doc_to_meta.get(item['document'], {}),
        } for item in reranked]

retrieval_engine = RetrievalEngine()
