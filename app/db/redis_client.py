import redis
from app.config import settings
from app.utils.logger import logger

class RedisClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connect()
        return cls._instance
    
    def _connect(self):
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            self.client.ping()
            logger.info("Redis连接成功")
        except Exception as e:
            logger.error(f"Redis连接失败: {str(e)}")
            self.client = None
    
    def get(self, key: str):
        if not self.client:
            return None
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis读取失败: {str(e)}")
            return None
    
    def set(self, key: str, value: str, ttl: int = None):
        if not self.client:
            return False
        try:
            ttl = ttl or settings.REDIS_TTL
            self.client.set(key, value, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Redis写入失败: {str(e)}")
            return False
    
    def setex(self, key: str, ttl: int, value: str):
        """设置带过期时间的键值"""
        if not self.client:
            return False
        try:
            self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.error(f"Redis setex失败: {str(e)}")
            return False
    
    def delete(self, key: str):
        if not self.client:
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis删除失败: {str(e)}")
            return False
    
    def exists(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis检查失败: {str(e)}")
            return False

redis_client = RedisClient()