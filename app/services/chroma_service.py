# ChromaDB 服务层
import chromadb
from chromadb.config import Settings
from app.config import settings
from app.utils.logger import logger

class ChromaService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        try:
            self.client = chromadb.PersistentClient(
                path=settings.CHROMA_PATH,
                settings=Settings(
                    anonymized_telemetry=False
                )
            )
            self.collection = self.client.get_or_create_collection("rag_documents")
            logger.info("ChromaDB初始化成功")
        except Exception as e:
            logger.error(f"ChromaDB初始化失败: {str(e)}")
            self.client = None
    
    def add_documents(self, documents: list, embeddings: list, metadatas: list = None, ids: list = None):
        if not self.client:
            return False
        try:
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"成功添加 {len(documents)} 个文档")
            return True
        except Exception as e:
            logger.error(f"ChromaDB添加文档失败: {str(e)}")
            return False
    
    def query(self, query_embedding: list, n_results: int = 3):
        if not self.client:
            return []
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            return [{
                'document': doc,
                'metadata': meta,
                'distance': dist
            } for doc, meta, dist in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )]
        except Exception as e:
            logger.error(f"ChromaDB查询失败: {str(e)}")
            return []
    
    def count(self) -> int:
        if not self.client:
            return 0
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"ChromaDB计数失败: {str(e)}")
            return 0
    
    def clear_collection(self):
        if not self.client:
            return False
        try:
            self.client.delete_collection("rag_documents")
            self.collection = self.client.create_collection("rag_documents")
            logger.info("ChromaDB集合已清空")
            return True
        except Exception as e:
            logger.error(f"ChromaDB清空失败: {str(e)}")
            return False

chroma_service = ChromaService()