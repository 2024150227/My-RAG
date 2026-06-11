# 内存服务层
import json
from app.db.redis_client import redis_client
from app.db.mysql_client import mysql_client
from app.config import settings
from app.utils.logger import logger

class MemoryService:
    def __init__(self):
        self.max_history_rounds = settings.MAX_HISTORY_ROUNDS
        self.cache = {}
    
    def get_short_term_memory(self, session_id: str) -> list:
        cached = self.cache.get(session_id)
        if cached:
            return cached
        
        redis_data = redis_client.get(f"session:{session_id}:history")
        if redis_data:
            try:
                history = json.loads(redis_data)
                self.cache[session_id] = history
                return history
            except json.JSONDecodeError:
                logger.error("Redis历史记录解析失败")
        
        return []
    
    def add_short_term_memory(self, session_id: str, user_input: str, assistant_output: str):
        history = self.get_short_term_memory(session_id)
        history.append({
            'user_input': user_input,
            'assistant_output': assistant_output
        })
        
        if len(history) > self.max_history_rounds:
            history = history[-self.max_history_rounds:]
        
        self.cache[session_id] = history
        
        try:
            redis_client.set(f"session:{session_id}:history", json.dumps(history))
        except Exception as e:
            logger.error(f"Redis保存历史失败: {str(e)}")
    
    def format_history_for_prompt(self, session_id: str) -> str:
        history = self.get_short_term_memory(session_id)
        if not history:
            return ""
        
        history_str = "历史对话：\n"
        for i, item in enumerate(history, 1):
            history_str += f"{i}. 用户：{item['user_input']}\n"
            history_str += f"   助手：{item['assistant_output']}\n"
        
        return history_str
    
    async def save_long_term_memory(self, session_id: str, user_input: str, assistant_output: str, context: str = None):
        mysql_client.save_conversation(session_id, user_input, assistant_output, context)
    
    def get_long_term_memory(self, session_id: str, limit: int = 100) -> list:
        return mysql_client.get_conversations(session_id, limit)
    
    def clear_memory(self, session_id: str):
        self.cache.pop(session_id, None)
        redis_client.delete(f"session:{session_id}:history")

memory_service = MemoryService()