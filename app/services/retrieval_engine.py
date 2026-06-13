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
        query_embedding = embedding_service.get_embedding(query)
        if not query_embedding:
            return []

        # user_id 不为空时按用户过滤；为空时不过滤（兼容老调用 / 系统级查询）
        where = {"user_id": user_id} if user_id else None
        vector_results = chroma_service.query(query_embedding, n_results=self.top_k * 2, where=where)
        
        if not vector_results:
            return []
        
        documents = [res['document'] for res in vector_results]
        
        bm25_results = self.bm25_search(query, documents, top_n=self.top_k * 2)
        bm25_docs = [res['document'] for res in bm25_results]
        
        combined_docs = list(set(documents + bm25_docs))
        
        if len(combined_docs) == 0:
            return []
        
        reranked = rerank_service.rerank(query, combined_docs, top_n=self.top_k)
        
        return [{
            'document': item['document'],
            'relevance_score': item['relevance_score']
        } for item in reranked]

retrieval_engine = RetrievalEngine()