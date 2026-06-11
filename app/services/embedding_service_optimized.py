# 嵌入服务层（优化版：异步+批处理+连接池）
import asyncio
from typing import List, Optional
from app.config import settings
from app.utils.logger import logger
from app.services.async_http_client import async_http_client

class EmbeddingService:
    def __init__(self):
        self.api_key = settings.SILICONFLOW_API_KEY
        self.api_url = settings.SILICONFLOW_EMBED_URL
        self.model_name = "BAAI/bge-m3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def get_embedding(self, text: str) -> List[float]:
        """异步获取单个文本的嵌入向量"""
        data = {
            "input": text,
            "model": self.model_name,
            "encoding_format": "float"
        }
        
        try:
            result = await async_http_client.post(self.api_url, headers=self.headers, json=data)
            
            if result and 'data' in result and len(result['data']) > 0:
                return result['data'][0]['embedding']
            else:
                logger.error("嵌入API返回格式错误")
                return []
        except Exception as e:
            logger.error(f"嵌入API调用失败: {str(e)}")
            return []
    
    async def get_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        批量异步获取多个文本的嵌入向量
        Args:
            texts: 文本列表
        Returns:
            嵌入向量列表
        """
        if not texts:
            return []
        
        # 如果只有一个文本，直接调用单个方法
        if len(texts) == 1:
            embedding = await self.get_embedding(texts[0])
            return [embedding] if embedding else [[]]
        
        # 批量请求：将所有文本合并到一个请求中
        data = {
            "input": texts,
            "model": self.model_name,
            "encoding_format": "float"
        }
        
        try:
            result = await async_http_client.post(self.api_url, headers=self.headers, json=data)
            
            if result and 'data' in result:
                embeddings = [item['embedding'] for item in result['data']]
                logger.info(f"批量获取嵌入向量成功: {len(embeddings)} 个")
                return embeddings
            else:
                logger.error("批量嵌入API返回格式错误")
                return [[] for _ in texts]
        except Exception as e:
            logger.error(f"批量嵌入API调用失败: {str(e)}")
            # 降级：逐个获取
            logger.info("降级为逐个获取嵌入向量")
            return await self._get_embeddings_fallback(texts)
    
    async def _get_embeddings_fallback(self, texts: List[str]) -> List[List[float]]:
        """降级方案：逐个获取嵌入向量"""
        tasks = [self.get_embedding(text) for text in texts]
        return await asyncio.gather(*tasks)
    
    # 同步方法（用于向后兼容）
    def get_embedding_sync(self, text: str) -> List[float]:
        """同步获取嵌入向量（向后兼容）"""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_embedding(text))
        except RuntimeError:
            # 如果没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_embedding(text))
            finally:
                loop.close()
    
    def get_batch_embeddings_sync(self, texts: List[str]) -> List[List[float]]:
        """同步批量获取嵌入向量（向后兼容）"""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_batch_embeddings(texts))
        except RuntimeError:
            # 如果没有事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_batch_embeddings(texts))
            finally:
                loop.close()

embedding_service = EmbeddingService()