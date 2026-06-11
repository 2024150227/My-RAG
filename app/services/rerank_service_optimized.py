# 重排服务层（优化版：异步+连接池）
from typing import List, Dict, Any
import asyncio
from app.config import settings
from app.utils.logger import logger
from app.services.async_http_client import async_http_client

class RerankServiceOptimized:
    def __init__(self):
        self.api_key = settings.SILICONFLOW_API_KEY
        self.api_url = settings.SILICONFLOW_RERANK_URL
        self.model_name = "BAAI/bge-reranker-v2-m3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def rerank(self, query: str, documents: List[str], top_n: int = 3) -> List[Dict[str, Any]]:
        """异步重排文档"""
        if not documents:
            logger.warning("重排服务收到空文档列表")
            return []
        
        data = {
            "query": query,
            "documents": documents,
            "model": self.model_name,
            "top_n": top_n
        }
        
        try:
            logger.info(f"开始重排，文档数: {len(documents)}, top_n: {top_n}")
            result = await async_http_client.post(self.api_url, headers=self.headers, json=data)
            
            if result and 'results' in result:
                reranked = []
                for item in result['results']:
                    if 'relevance_score' in item:
                        idx = item.get('index', 0)
                        document = item.get('document')
                        if document is None and idx < len(documents):
                            document = documents[idx]
                        reranked.append({
                            'document': document,
                            'relevance_score': item['relevance_score'],
                            'index': idx
                        })
                logger.info(f"重排完成，返回 {len(reranked)} 个结果")
                return sorted(reranked, key=lambda x: x['relevance_score'], reverse=True)
            else:
                logger.error(f"重排API返回格式错误: {result}")
                # 如果重排失败，返回原始文档
                return [{'document': doc, 'relevance_score': 1.0, 'index': i} for i, doc in enumerate(documents[:top_n])]
        except Exception as e:
            logger.error(f"重排API调用失败: {str(e)}")
            # 如果重排失败，返回原始文档
            return [{'document': doc, 'relevance_score': 1.0, 'index': i} for i, doc in enumerate(documents[:top_n])]
    
    async def batch_rerank(self, queries: List[str], documents_list: List[List[str]], top_n: int = 3) -> List[List[Dict[str, Any]]]:
        """
        批量异步重排多个查询
        Args:
            queries: 查询列表
            documents_list: 文档列表的列表
            top_n: 返回的文档数量
        Returns:
            重排结果列表
        """
        if not queries or not documents_list:
            return []
        
        if len(queries) != len(documents_list):
            logger.error("查询数量和文档列表数量不匹配")
            return []
        
        # 创建异步任务
        tasks = [
            self.rerank(query, docs, top_n)
            for query, docs in zip(queries, documents_list)
        ]
        
        # 并发执行所有重排任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"重排任务 {i} 失败: {str(result)}")
                # 返回原始文档
                docs = documents_list[i]
                processed_results.append([
                    {'document': doc, 'relevance_score': 1.0, 'index': j}
                    for j, doc in enumerate(docs[:top_n])
                ])
            else:
                processed_results.append(result)
        
        return processed_results
    
    # 同步方法（用于向后兼容）
    def rerank_sync(self, query: str, documents: List[str], top_n: int = 3) -> List[Dict[str, Any]]:
        """同步重排（向后兼容）"""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.rerank(query, documents, top_n))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.rerank(query, documents, top_n))
            finally:
                loop.close()

rerank_service_optimized = RerankServiceOptimized()