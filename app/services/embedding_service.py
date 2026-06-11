import requests
import json
from app.config import settings
from app.utils.logger import logger

class EmbeddingService:
    def __init__(self):
        self.api_key = settings.SILICONFLOW_API_KEY
        self.api_url = settings.SILICONFLOW_EMBED_URL
        self.model_name = "BAAI/bge-m3"
    
    def get_embedding(self, text: str) -> list:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "input": text,
            "model": self.model_name,
            "encoding_format": "float"
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if 'data' in result and len(result['data']) > 0:
                return result['data'][0]['embedding']
            else:
                logger.error("嵌入API返回格式错误")
                return []
        except requests.exceptions.RequestException as e:
            logger.error(f"嵌入API调用失败: {str(e)}")
            return []
    
    def get_batch_embeddings(self, texts: list) -> list:
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text)
            if embedding:
                embeddings.append(embedding)
            else:
                embeddings.append([])
        return embeddings

embedding_service = EmbeddingService()