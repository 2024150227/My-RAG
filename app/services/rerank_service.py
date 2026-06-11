# 重排服务层
import requests
from app.config import settings
from app.utils.logger import logger

class RerankService:
    def __init__(self):
        self.api_key = settings.SILICONFLOW_API_KEY
        self.api_url = settings.SILICONFLOW_RERANK_URL
        self.model_name = "BAAI/bge-reranker-v2-m3"
    
    def rerank(self, query: str, documents: list, top_n: int = 3) -> list:
        if not documents:
            logger.warning("重排服务收到空文档列表")
            return []
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "query": query,
            "documents": documents,
            "model": self.model_name,
            "top_n": top_n
        }
        
        try:
            logger.info(f"开始重排，文档数: {len(documents)}, top_n: {top_n}")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"重排API返回: {result}")
            
            if 'results' in result:
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
        except requests.exceptions.RequestException as e:
            logger.error(f"重排API调用失败: {str(e)}")
            # 如果重排失败，返回原始文档
            return [{'document': doc, 'relevance_score': 1.0, 'index': i} for i, doc in enumerate(documents[:top_n])]

rerank_service = RerankService()