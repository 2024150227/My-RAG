import requests
from app.config import settings
from app.utils.logger import logger


class EmbeddingService:
    """嵌入服务，支持 siliconflow / ark 两种 provider，二者都是 OpenAI 协议兼容。

    切换通过 ``EMBED_PROVIDER`` 环境变量；默认 ``ark``（火山方舟 Doubao Embedding）。

    ⚠️  换 provider = 换模型 = 向量维度可能不同；切换前必须清空 ChromaDB 重新入库，
        否则旧向量与新 query 向量做余弦相似度会得到无意义的结果。
    """

    def __init__(self):
        self.provider = settings.EMBED_PROVIDER

        # 硅基流动
        self.sf_api_key = settings.SILICONFLOW_API_KEY
        self.sf_url = settings.SILICONFLOW_EMBED_URL
        self.sf_model = "BAAI/bge-m3"

        # 火山方舟
        self.ark_api_key = settings.ARK_API_KEY
        self.ark_url = f"{settings.ARK_BASE_URL.rstrip('/')}/embeddings"
        self.ark_model = settings.ARK_EMBED_MODEL

        logger.info(
            f"EmbeddingService 初始化: provider={self.provider}, "
            f"model={self.ark_model if self.provider == 'ark' else self.sf_model}"
        )

    def get_embedding(self, text: str) -> list:
        if self.provider == "ark":
            return self._embed_ark(text)
        return self._embed_siliconflow(text)

    def get_batch_embeddings(self, texts: list) -> list:
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text)
            embeddings.append(embedding if embedding else [])
        return embeddings

    # ----------------------- 火山方舟 -----------------------
    def _embed_ark(self, text: str) -> list:
        if not self.ark_api_key:
            logger.error("ARK_API_KEY 未配置")
            return []

        headers = {
            "Authorization": f"Bearer {self.ark_api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.ark_model,
            "input": text,
            "encoding_format": "float",
        }

        try:
            response = requests.post(self.ark_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            if 'data' in result and len(result['data']) > 0:
                return result['data'][0]['embedding']
            logger.error(f"嵌入API返回格式错误(ark): {result}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"嵌入API调用失败(ark): {str(e)}")
            return []

    # ----------------------- 硅基流动 -----------------------
    def _embed_siliconflow(self, text: str) -> list:
        if not self.sf_api_key:
            logger.error("SILICONFLOW_API_KEY 未配置")
            return []

        headers = {
            "Authorization": f"Bearer {self.sf_api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "input": text,
            "model": self.sf_model,
            "encoding_format": "float",
        }

        try:
            response = requests.post(self.sf_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            if 'data' in result and len(result['data']) > 0:
                return result['data'][0]['embedding']
            logger.error(f"嵌入API返回格式错误(siliconflow): {result}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"嵌入API调用失败(siliconflow): {str(e)}")
            return []


embedding_service = EmbeddingService()
