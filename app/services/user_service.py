# 用户服务层 - 账号体系管理
import json
import hashlib
import uuid
from datetime import datetime
from app.db.redis_client import redis_client
from app.utils.logger import logger

class UserService:
    def __init__(self):
        self.user_prefix = "user:"
        self.session_prefix = "session:"
        self.token_prefix = "token:"
    
    def _hash_password(self, password: str) -> str:
        """密码哈希处理"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _generate_token(self) -> str:
        """生成唯一令牌"""
        return str(uuid.uuid4())
    
    def register(self, username: str, password: str) -> dict:
        """
        用户注册
        Args:
            username: 用户名
            password: 密码
        Returns:
            {"success": bool, "message": str, "user_id": str}
        """
        try:
            # 检查用户是否已存在
            existing_user = redis_client.get(f"{self.user_prefix}{username}")
            if existing_user:
                return {"success": False, "message": "用户名已存在"}
            
            # 生成用户ID
            user_id = str(uuid.uuid4())
            
            # 创建用户数据
            user_data = {
                "user_id": user_id,
                "username": username,
                "password": self._hash_password(password),
                "created_at": datetime.now().isoformat(),
                "last_login": None
            }
            
            # 存储用户信息到Redis
            redis_client.set(f"{self.user_prefix}{username}", json.dumps(user_data))
            redis_client.set(f"{self.user_prefix}id:{user_id}", json.dumps(user_data))
            
            logger.info(f"用户注册成功: {username}, user_id: {user_id}")
            return {"success": True, "message": "注册成功", "user_id": user_id}
            
        except Exception as e:
            logger.error(f"用户注册失败: {str(e)}")
            return {"success": False, "message": f"注册失败: {str(e)}"}
    
    def login(self, username: str, password: str) -> dict:
        """
        用户登录
        Args:
            username: 用户名
            password: 密码
        Returns:
            {"success": bool, "message": str, "token": str, "user_id": str}
        """
        try:
            # 获取用户信息
            user_data_str = redis_client.get(f"{self.user_prefix}{username}")
            if not user_data_str:
                return {"success": False, "message": "用户不存在"}
            
            user_data = json.loads(user_data_str)
            
            # 验证密码
            if user_data["password"] != self._hash_password(password):
                return {"success": False, "message": "密码错误"}
            
            # 生成登录令牌
            token = self._generate_token()
            user_id = user_data["user_id"]
            
            # 更新最后登录时间
            user_data["last_login"] = datetime.now().isoformat()
            redis_client.set(f"{self.user_prefix}{username}", json.dumps(user_data))
            redis_client.set(f"{self.user_prefix}id:{user_id}", json.dumps(user_data))
            
            # 存储令牌，有效期24小时
            token_data = {
                "user_id": user_id,
                "username": username,
                "created_at": datetime.now().isoformat()
            }
            redis_client.setex(f"{self.token_prefix}{token}", 86400, json.dumps(token_data))
            
            logger.info(f"用户登录成功: {username}, token: {token}")
            return {
                "success": True,
                "message": "登录成功",
                "token": token,
                "user_id": user_id,
                "username": username
            }
            
        except Exception as e:
            logger.error(f"用户登录失败: {str(e)}")
            return {"success": False, "message": f"登录失败: {str(e)}"}
    
    def verify_token(self, token: str) -> dict:
        """
        验证登录令牌
        Args:
            token: 登录令牌
        Returns:
            {"valid": bool, "user_id": str, "username": str}
        """
        try:
            token_data_str = redis_client.get(f"{self.token_prefix}{token}")
            if not token_data_str:
                return {"valid": False, "message": "令牌无效或已过期"}
            
            token_data = json.loads(token_data_str)
            return {
                "valid": True,
                "user_id": token_data["user_id"],
                "username": token_data["username"]
            }
            
        except Exception as e:
            logger.error(f"令牌验证失败: {str(e)}")
            return {"valid": False, "message": f"验证失败: {str(e)}"}
    
    def logout(self, token: str) -> dict:
        """
        用户登出
        Args:
            token: 登录令牌
        Returns:
            {"success": bool, "message": str}
        """
        try:
            redis_client.delete(f"{self.token_prefix}{token}")
            logger.info(f"用户登出成功")
            return {"success": True, "message": "登出成功"}
        except Exception as e:
            logger.error(f"用户登出失败: {str(e)}")
            return {"success": False, "message": f"登出失败: {str(e)}"}
    
    def get_user_by_id(self, user_id: str) -> dict:
        """
        根据用户ID获取用户信息
        Args:
            user_id: 用户ID
        Returns:
            用户信息字典
        """
        try:
            user_data_str = redis_client.get(f"{self.user_prefix}id:{user_id}")
            if not user_data_str:
                return None
            
            user_data = json.loads(user_data_str)
            # 移除密码字段
            user_data.pop("password", None)
            return user_data
            
        except Exception as e:
            logger.error(f"获取用户信息失败: {str(e)}")
            return None
    
    def get_user_session(self, user_id: str) -> str:
        """
        获取用户当前会话ID
        Args:
            user_id: 用户ID
        Returns:
            会话ID
        """
        try:
            session_id = redis_client.get(f"{self.session_prefix}current:{user_id}")
            if not session_id:
                # 创建新会话
                session_id = f"{user_id}:{str(uuid.uuid4())}"
                redis_client.set(f"{self.session_prefix}current:{user_id}", session_id)
            return session_id
        except Exception as e:
            logger.error(f"获取用户会话失败: {str(e)}")
            return f"{user_id}:default"
    
    def create_new_session(self, user_id: str) -> str:
        """
        创建新会话
        Args:
            user_id: 用户ID
        Returns:
            新会话ID
        """
        try:
            session_id = f"{user_id}:{str(uuid.uuid4())}"
            redis_client.set(f"{self.session_prefix}current:{user_id}", session_id)
            logger.info(f"创建新会话: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"创建新会话失败: {str(e)}")
            return f"{user_id}:default"

user_service = UserService()