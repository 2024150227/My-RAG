import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # 硅基流动 API 配置（rerank 仍用，embedding/LLM 可选）
    SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
    SILICONFLOW_EMBED_URL = os.getenv("SILICONFLOW_EMBED_URL", "https://api.siliconflow.cn/v1/embeddings")
    SILICONFLOW_RERANK_URL = os.getenv("SILICONFLOW_RERANK_URL", "https://api.siliconflow.cn/v1/rerank")

    # 火山方舟（Ark）配置
    # 标准 OpenAI 兼容端点是 /api/v3，不是 /api/coding（后者是 Anthropic 协议兼容，给 Claude Code 用的）
    ARK_API_KEY = os.getenv("ARK_API_KEY", "")
    ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    ARK_LLM_MODEL = os.getenv("ARK_LLM_MODEL", "doubao-1-5-pro-32k-250115")
    ARK_EMBED_MODEL = os.getenv("ARK_EMBED_MODEL", "doubao-embedding-large-text-240915")

    # Ollama配置
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen:latest")

    # LLM 提供方：ollama（本地） / siliconflow（云端 API） / ark（火山方舟，默认）
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ark").lower()
    SILICONFLOW_LLM_URL = os.getenv("SILICONFLOW_LLM_URL", "https://api.siliconflow.cn/v1/chat/completions")
    SILICONFLOW_LLM_MODEL = os.getenv("SILICONFLOW_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")

    # Embedding 提供方：siliconflow / ark（默认 ark）
    # 注意：换 embedding 模型 = 向量维度可能不一致，必须清空 ChromaDB 重新入库
    EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "ark").lower()

    # Gradio 访问鉴权（用户名,密码；为空表示不启用）
    GRADIO_AUTH_USER = os.getenv("GRADIO_AUTH_USER", "")
    GRADIO_AUTH_PASSWORD = os.getenv("GRADIO_AUTH_PASSWORD", "")
    
    # Redis配置
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_TTL = int(os.getenv("REDIS_TTL", "21600"))
    
    # MySQL配置
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "rag_db")
    
    # ChromaDB配置
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./chromadb_data")
    
    # FastAPI配置
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    # LLM参数
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.4"))
    TOP_K = int(os.getenv("TOP_K", "3"))
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "500"))
    
    # 文档处理配置
    MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP_RATIO = float(os.getenv("CHUNK_OVERLAP_RATIO", "0.15"))
    
    # 会话配置
    MAX_HISTORY_ROUNDS = int(os.getenv("MAX_HISTORY_ROUNDS", "7"))
    
    # API URL配置
    API_URL = os.getenv("API_URL", "http://localhost:8000")

settings = Settings()