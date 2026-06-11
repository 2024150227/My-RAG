# 异步HTTP客户端服务（连接池）
import httpx
from typing import Optional, Dict, Any, List
from app.config import settings
from app.utils.logger import logger

class AsyncHTTPClient:
    """异步HTTP客户端，使用连接池优化性能"""
    
    _instance = None
    _client: Optional[httpx.AsyncClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        """初始化异步HTTP客户端"""
        try:
            # 配置连接池参数
            limits = httpx.Limits(
                max_keepalive_connections=20,  # 最大保持连接数
                max_connections=100,           # 最大连接数
                keepalive_expiry=30.0          # 连接保持时间（秒）
            )
            
            # 配置超时
            timeout = httpx.Timeout(
                connect=10.0,      # 连接超时
                read=30.0,         # 读取超时
                write=10.0,        # 写入超时
                pool=5.0           # 连接池获取超时
            )
            
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                http2=True,        # 启用HTTP/2
                verify=True        # 验证SSL证书
            )
            
            logger.info("异步HTTP客户端初始化成功")
        except Exception as e:
            logger.error(f"异步HTTP客户端初始化失败: {str(e)}")
            self._client = None
    
    async def get(self, url: str, headers: Optional[Dict[str, str]] = None, 
                  params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """异步GET请求"""
        if not self._client:
            logger.error("HTTP客户端未初始化")
            return None
        
        try:
            response = await self._client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"GET请求失败: {str(e)}")
            return None
    
    async def post(self, url: str, headers: Optional[Dict[str, str]] = None,
                   data: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """异步POST请求"""
        if not self._client:
            logger.error("HTTP客户端未初始化")
            return None
        
        try:
            response = await self._client.post(url, headers=headers, data=data, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"POST请求失败: {str(e)}")
            return None
    
    async def batch_post(self, url: str, headers: Optional[Dict[str, str]] = None,
                         requests_data: List[Dict[str, Any]] = None) -> List[Optional[Dict[str, Any]]]:
        """
        批量异步POST请求
        Args:
            url: 请求URL
            headers: 请求头
            requests_data: 请求数据列表
        Returns:
            响应结果列表
        """
        if not self._client:
            logger.error("HTTP客户端未初始化")
            return [None] * len(requests_data)
        
        if not requests_data:
            return []
        
        try:
            # 创建异步任务列表
            tasks = [
                self._client.post(url, headers=headers, json=data)
                for data in requests_data
            ]
            
            # 并发执行所有请求
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理响应
            results = []
            for response in responses:
                if isinstance(response, Exception):
                    logger.error(f"批量请求失败: {str(response)}")
                    results.append(None)
                else:
                    try:
                        response.raise_for_status()
                        results.append(response.json())
                    except Exception as e:
                        logger.error(f"响应解析失败: {str(e)}")
                        results.append(None)
            
            return results
        except Exception as e:
            logger.error(f"批量POST请求失败: {str(e)}")
            return [None] * len(requests_data)
    
    async def close(self):
        """关闭HTTP客户端"""
        if self._client:
            await self._client.aclose()
            logger.info("HTTP客户端已关闭")

# 全局异步HTTP客户端
async_http_client = AsyncHTTPClient()

# 导入asyncio用于批量请求
import asyncio