import requests
from app.config import settings
from app.utils.logger import logger

SYSTEM_PROMPT = """
你是专业的企业文档分析师，严格依据提供的文档内容进行回答、总结与润色。

工作规范：
1. 回答优先分条梳理内容，逻辑清晰、简洁易懂；
2. 严禁编造文档以外的信息，保证答案忠实于原文；
3. 仅围绕给定文档片段作答，不输出无关内容。

参考示例：
用户提问：交互式建模（DSW）计费方式是什么？
模型回复：交互式建模（DSW）计费包含四类：按量付费、预付费、资源包、节省计划。
"""

class LLMService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model_name = settings.OLLAMA_MODEL
        self.temperature = settings.TEMPERATURE
        self.max_tokens = settings.MAX_TOKENS
    
    def generate(self, prompt: str, context: str = "") -> str:
        if context:
            full_prompt = f"{SYSTEM_PROMPT}\n\n参考文档：\n{context}\n\n用户问题：{prompt}\n\n回答："
        else:
            full_prompt = f"{SYSTEM_PROMPT}\n\n用户问题：{prompt}\n\n回答："
        
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                headers=headers,
                json=data,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            if 'response' in result:
                return result['response'].strip()
            else:
                logger.error("LLM返回格式错误")
                return "抱歉，未能生成回答"
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM调用失败: {str(e)}")
            return f"LLM调用失败: {str(e)}"

llm_service = LLMService()