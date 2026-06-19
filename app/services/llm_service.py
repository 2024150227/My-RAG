import codecs
import json
import requests
from typing import Iterator
from app.config import settings
from app.utils.logger import logger


def _iter_utf8_lines(resp, chunk_size: int = 1024) -> Iterator[str]:
    """按 UTF-8 增量解码 + 按 \\n 拆行。

    替代 ``resp.iter_lines(decode_unicode=True)``——后者按 chunk 边界单独解码，
    一个汉字 3 字节如果被切在两个 chunk 间会出乱码。增量解码器会把残字节
    缓存住，等下一个 chunk 拼齐再 emit，保证多字节字符不被切坏。
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buffer = ""
    for chunk in resp.iter_content(chunk_size=chunk_size):
        if not chunk:
            continue
        buffer += decoder.decode(chunk)
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield line.rstrip("\r")
    tail = decoder.decode(b"", final=True)
    if tail:
        buffer += tail
    if buffer:
        yield buffer.rstrip("\r")

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


def _build_prompt(prompt: str, context: str) -> str:
    if context:
        return f"{SYSTEM_PROMPT}\n\n参考文档：\n{context}\n\n用户问题：{prompt}\n\n回答："
    return f"{SYSTEM_PROMPT}\n\n用户问题：{prompt}\n\n回答："


class LLMService:
    """LLM 服务，支持 ollama（本地）/ siliconflow / ark（火山方舟） 三种 provider。

    siliconflow 与 ark 都是 OpenAI 兼容协议，结构几乎一致（chat/completions + delta 流式）。
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.temperature = settings.TEMPERATURE
        self.max_tokens = settings.MAX_TOKENS

        # ollama
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.ollama_model = settings.OLLAMA_MODEL

        # siliconflow
        self.sf_url = settings.SILICONFLOW_LLM_URL
        self.sf_model = settings.SILICONFLOW_LLM_MODEL
        self.sf_api_key = settings.SILICONFLOW_API_KEY

        # 火山方舟（OpenAI 协议兼容；端点是 /api/v3/chat/completions）
        self.ark_url = f"{settings.ARK_BASE_URL.rstrip('/')}/chat/completions"
        self.ark_model = settings.ARK_LLM_MODEL
        self.ark_api_key = settings.ARK_API_KEY

        logger.info(f"LLMService 初始化: provider={self.provider}")

    def generate(self, prompt: str, context: str = "") -> str:
        full_prompt = _build_prompt(prompt, context)
        if self.provider == "ark":
            return self._generate_openai_compatible(
                full_prompt,
                url=self.ark_url,
                api_key=self.ark_api_key,
                model=self.ark_model,
                provider_name="ark",
            )
        if self.provider == "siliconflow":
            return self._generate_openai_compatible(
                full_prompt,
                url=self.sf_url,
                api_key=self.sf_api_key,
                model=self.sf_model,
                provider_name="siliconflow",
            )
        return self._generate_ollama(full_prompt)

    # ----------------------- Ollama -----------------------
    def _generate_ollama(self, full_prompt: str) -> str:
        data = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                headers={"Content-Type": "application/json"},
                json=data,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            if "response" in result:
                return result["response"].strip()
            logger.error("LLM返回格式错误")
            return "抱歉，未能生成回答"
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM调用失败(ollama): {str(e)}")
            return f"LLM调用失败: {str(e)}"

    # --------------------- OpenAI 兼容（siliconflow / ark 共用） ---------------------
    def _generate_openai_compatible(
        self,
        full_prompt: str,
        url: str,
        api_key: str,
        model: str,
        provider_name: str,
    ) -> str:
        """同步生成 —— OpenAI 兼容协议的统一实现。siliconflow / 火山方舟都走这个方法。"""
        if not api_key:
            logger.error(f"{provider_name.upper()}_API_KEY 未配置")
            return f"LLM调用失败: {provider_name} API Key 未配置"

        data = {
            "model": model,
            "messages": [{"role": "user", "content": full_prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM调用失败({provider_name}): {str(e)}")
            return f"LLM调用失败: {str(e)}"
        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"LLM返回解析失败({provider_name}): {str(e)}")
            return "抱歉，未能生成回答"

    # --------------------- SiliconFlow（保留旧入口名，便于回归测试） ---------------------
    def _generate_siliconflow(self, full_prompt: str) -> str:
        return self._generate_openai_compatible(
            full_prompt,
            url=self.sf_url,
            api_key=self.sf_api_key,
            model=self.sf_model,
            provider_name="siliconflow",
        )

    # ==================== 流式生成 ====================

    def generate_stream(self, prompt: str, context: str = "") -> Iterator[str]:
        """流式生成回答，逐 token 返回字符串增量。

        - ollama         : POST /api/generate stream=True，返回逐行 JSON
        - siliconflow / ark : POST /v1/chat/completions stream=True，返回 SSE 'data: {...}'
        """
        full_prompt = _build_prompt(prompt, context)
        if self.provider == "ark":
            yield from self._stream_openai_compatible(
                full_prompt,
                url=self.ark_url,
                api_key=self.ark_api_key,
                model=self.ark_model,
                provider_name="ark",
            )
        elif self.provider == "siliconflow":
            yield from self._stream_openai_compatible(
                full_prompt,
                url=self.sf_url,
                api_key=self.sf_api_key,
                model=self.sf_model,
                provider_name="siliconflow",
            )
        else:
            yield from self._stream_ollama(full_prompt)

    # ----------------------- Ollama 流式 -----------------------
    def _stream_ollama(self, full_prompt: str) -> Iterator[str]:
        data = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        try:
            with requests.post(
                f"{self.ollama_base_url}/api/generate",
                headers={"Content-Type": "application/json"},
                json=data,
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                for line in _iter_utf8_lines(resp):
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM 流式调用失败(ollama): {str(e)}")
            yield f"\n[流式调用失败: {str(e)}]"

    # --------------------- OpenAI 兼容流式（siliconflow / ark 共用） ---------------------
    def _stream_openai_compatible(
        self,
        full_prompt: str,
        url: str,
        api_key: str,
        model: str,
        provider_name: str,
    ) -> Iterator[str]:
        """流式生成 —— OpenAI 兼容协议的统一实现。

        SSE 帧格式：``data: {"choices":[{"delta":{"content":"..."}}]}\\n\\n``，
        最后一帧是 ``data: [DONE]``。
        """
        if not api_key:
            yield f"[流式调用失败: {provider_name} API Key 未配置]"
            return

        data = {
            "model": model,
            "messages": [{"role": "user", "content": full_prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            with requests.post(url, headers=headers, json=data, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                for raw in _iter_utf8_lines(resp):
                    if not raw or not raw.startswith("data:"):
                        continue
                    payload = raw[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk["choices"][0]["delta"].get("content", "")
                    except (KeyError, IndexError):
                        delta = ""
                    if delta:
                        yield delta
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM 流式调用失败({provider_name}): {str(e)}")
            yield f"\n[流式调用失败: {str(e)}]"

    # --------------------- SiliconFlow 流式（保留旧入口名） ---------------------
    def _stream_siliconflow(self, full_prompt: str) -> Iterator[str]:
        yield from self._stream_openai_compatible(
            full_prompt,
            url=self.sf_url,
            api_key=self.sf_api_key,
            model=self.sf_model,
            provider_name="siliconflow",
        )


llm_service = LLMService()
