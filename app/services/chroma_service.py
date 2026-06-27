# ChromaDB 服务层
import chromadb
from chromadb.config import Settings
from app.config import settings
from app.utils.logger import logger

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    logger.warning("numpy 未安装，暴力 KNN 将使用纯 Python 模式（小数据集无影响）")

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
    
    def query(self, query_embedding: list, n_results: int = 3, where: dict = None):
        """HNSW 索引检索（近似，速度快），保留给需要高性能的场景。"""
        if not self.client:
            return []
        try:
            kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
            }
            if where:
                kwargs["where"] = where
            results = self.collection.query(**kwargs)
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

    def knn_search(self, query_embedding: list, n_results: int = 3, where: dict = None) -> list:
        """暴力 KNN 检索——全量加载所有向量，逐一算余弦距离。

        文档少时用这个，精度 100%（相比 HNSW 的近似搜索）。
        文档多（>10 万）后建议切回 self.query() 用 HNSW 索引。
        """
        if not self.client:
            return []

        try:
            # 带 where 过滤时，用 get + where；不过滤时全量加载更高效
            kwargs_get = {"include": ["embeddings", "documents", "metadatas"]}
            if where:
                kwargs_get["where"] = where

            all_data = self.collection.get(**kwargs_get)

            ids = all_data.get("ids", []) or []
            docs = all_data.get("documents", []) or []
            metas = all_data.get("metadatas", []) or []
            embs = all_data.get("embeddings", []) or []

            if not embs:
                return []

            # numpy 加速 vs 纯 Python 回退
            if _HAS_NUMPY:
                q = np.array(query_embedding, dtype=np.float32)
                v = np.array(embs, dtype=np.float32)
                q_norm = q / np.linalg.norm(q)
                v_norms = v / np.linalg.norm(v, axis=1, keepdims=True)
                sims = np.dot(v_norms, q_norm)
                dists = 1 - sims
                top_idx = np.argsort(dists)[:n_results]
                top_dists = [float(dists[i]) for i in top_idx]
            else:
                def _cos_dist(a, b):
                    dot = sum(x * y for x, y in zip(a, b))
                    na = sum(x * x for x in a) ** 0.5
                    nb = sum(x * x for x in b) ** 0.5
                    return 1 - dot / (na * nb) if na and nb else 1.0

                scored = [(i, _cos_dist(query_embedding, embs[i])) for i in range(len(embs))]
                scored.sort(key=lambda x: x[1])
                top_idx, top_dists = zip(*scored[:n_results]) if scored[:n_results] else ([], [])

            return [{
                'document': docs[i],
                'metadata': metas[i] if i < len(metas) else {},
                'distance': top_dists[j],
            } for j, i in enumerate(top_idx)]

        except Exception as e:
            logger.error(f"ChromaDB暴力KNN失败: {str(e)}")
            return []

    def count(self, user_id: str = None) -> int:
        if not self.client:
            return 0
        try:
            if user_id:
                # 按 user_id 过滤计数
                results = self.collection.get(where={"user_id": user_id})
                return len(results.get("ids", []))
            return self.collection.count()
        except Exception as e:
            logger.error(f"ChromaDB计数失败: {str(e)}")
            return 0

    def get_by_filename_full(self, user_id: str, filename: str) -> list:
        """获取某文件的所有 chunk，含 id / document / metadata 完整信息。

        返回 ``[{id, document, metadata}, ...]``，用于增量更新的新旧比对；
        找不到 / 出错时返回 []。
        """
        if not self.client:
            return []
        try:
            res = self.collection.get(
                where={"$and": [{"user_id": user_id}, {"filename": filename}]},
                include=["documents", "metadatas"],
            )
            ids = res.get("ids", []) or []
            docs = res.get("documents", []) or []
            metas = res.get("metadatas", []) or []
            return [
                {"id": ids[i], "document": docs[i], "metadata": metas[i] or {}}
                for i in range(len(ids))
            ]
        except Exception as e:
            logger.error(f"ChromaDB 按文件名查询失败: {str(e)}")
            return []

    def upsert_documents(
        self, documents: list, embeddings: list, metadatas: list = None, ids: list = None
    ) -> bool:
        """更新或插入文档（ChromaDB 原生 upsert）。

        ID 已存在 → 覆盖；不存在 → 新增。
        比先 delete 再 add 更高效，且不会出现中间态。
        """
        if not self.client:
            return False
        try:
            self.collection.upsert(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info(f"Upsert {len(documents)} 个 chunk")
            return True
        except Exception as e:
            logger.error(f"ChromaDB upsert 失败: {str(e)}")
            return False

    def delete_by_user(self, user_id: str) -> bool:
        """删除指定用户的所有文档"""
        if not self.client:
            return False
        try:
            self.collection.delete(where={"user_id": user_id})
            logger.info(f"已删除用户 {user_id} 的所有文档")
            return True
        except Exception as e:
            logger.error(f"ChromaDB按用户删除失败: {str(e)}")
            return False

    def exists_filename(self, user_id: str, filename: str) -> bool:
        """检查指定用户的知识库中是否已存在同名文件"""
        if not self.client:
            return False
        try:
            res = self.collection.get(
                where={"$and": [{"user_id": user_id}, {"filename": filename}]},
                limit=1,
            )
            return bool(res.get("ids"))
        except Exception as e:
            logger.error(f"ChromaDB 查询同名文件失败: {str(e)}")
            return False

    def delete_by_filename(self, user_id: str, filename: str) -> int:
        """删除指定用户名下指定文件名的所有 chunk，返回删除的 chunk 数。"""
        if not self.client:
            return 0
        try:
            res = self.collection.get(
                where={"$and": [{"user_id": user_id}, {"filename": filename}]}
            )
            ids = res.get("ids", []) or []
            if not ids:
                return 0
            self.collection.delete(ids=ids)
            logger.info(f"已删除用户 {user_id} 文件 {filename} 的 {len(ids)} 个 chunk")
            return len(ids)
        except Exception as e:
            logger.error(f"ChromaDB 按文件名删除失败: {str(e)}")
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