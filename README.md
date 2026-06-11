# 企业级RAG知识库系统

基于LangChain + ChromaDB + Ollama构建的企业级检索增强生成(RAG)知识库系统，支持文档上传、智能问答、语义检索等功能。

## 功能特性

- **文档管理**：支持Markdown、PDF、TXT、Excel等多种格式文档上传
- **智能检索**：混合检索（向量检索 + BM25）+ Rerank重排
- **语义分块**：基于Markdown结构的智能文档分块
- **会话管理**：支持多轮对话，保持上下文记忆
- **可视化界面**：基于Gradio的友好前端界面

## 技术栈

- **框架**: FastAPI + Gradio
- **向量数据库**: ChromaDB
- **大语言模型**: Ollama (Qwen)
- **嵌入模型**: BAAI/bge-m3
- **重排序模型**: BAAI/bge-reranker-v2-m3
- **缓存**: Redis

## 项目结构

```
MY-RAG/
├── app/
│   ├── api/              # API路由
│   ├── db/               # 数据库客户端
│   ├── frontend/         # Gradio前端
│   ├── services/         # 核心服务
│   │   ├── chroma_service.py      # ChromaDB服务
│   │   ├── document_processor.py  # 文档处理
│   │   ├── embedding_service.py   # 嵌入服务
│   │   ├── llm_service.py         # LLM服务
│   │   ├── retrieval_engine.py    # 检索引擎
│   │   └── rerank_service.py      # 重排序服务
│   ├── utils/            # 工具类
│   ├── config.py         # 配置管理
│   └── main.py           # 应用入口
├── chromadb_data/        # ChromaDB数据目录
├── scripts/              # 脚本文件
│   ├── init_knowledge.py # 知识库初始化
│   └── start_api.py      # 启动API服务
├── tests/                # 测试文件
├── .env                  # 环境变量配置
├── docker-compose.yml    # Docker配置
└── requirements.txt      # 依赖清单
```

## 快速开始

### 环境要求

- Python >= 3.10
- Ollama >= 0.30.0
- Redis（可选，用于会话缓存）

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd MY-RAG
```

2. **创建虚拟环境**
```bash
python -m venv venv
# Windows
venv\Scripts\Activate.ps1
# Linux/Mac
source venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置环境变量**
```bash
cp .env.example .env
# 编辑.env文件，配置API密钥等参数
```

5. **启动Ollama服务**
```bash
ollama pull qwen:latest
ollama serve
```

6. **初始化知识库**
```bash
python scripts/init_knowledge.py
```

7. **启动服务**
```bash
# 启动API服务
python scripts/start_api.py

# 启动前端服务（新终端）
python app/frontend/gradio_app.py
```

## 配置说明

### .env 文件配置

```ini
# 硅基流动API配置
SILICONFLOW_API_KEY=your-api-key
SILICONFLOW_EMBED_URL=https://api.siliconflow.cn/v1/embeddings
SILICONFLOW_RERANK_URL=https://api.siliconflow.cn/v1/rerank

# Ollama配置
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen:latest

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379

# ChromaDB配置
CHROMA_PATH=./chromadb_data

# API配置
API_HOST=0.0.0.0
API_PORT=8000

# LLM参数
TEMPERATURE=0.4
TOP_K=3
MAX_TOKENS=500
```

## API接口

### 查询接口
```http
POST /query
Content-Type: application/json

{
    "query": "您的问题",
    "session_id": "可选，会话ID",
    "top_k": 3
}
```

### 上传接口
```http
POST /upload
Content-Type: multipart/form-data

file: <文件>
```

### 统计接口
```http
GET /stats
```

### 清空接口
```http
DELETE /clear
```

## 使用示例

### 前端界面

启动服务后，访问 http://localhost:7860 即可使用可视化界面：

1. **文档上传**：点击"上传到知识库"按钮上传文档
2. **智能问答**：在输入框中输入问题，点击提交即可获得回答
3. **会话管理**：系统自动维护会话上下文

### API调用

```python
import requests

# 查询
response = requests.post(
    "http://localhost:8000/query",
    json={"query": "交互式建模是什么？"}
)
print(response.json())

# 上传文件
with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/upload",
        files={"file": f}
    )
print(response.json())
```

## 检索策略

系统采用混合检索策略：

1. **向量检索**：使用BGE-M3模型将查询和文档向量化，进行相似度匹配
2. **BM25检索**：基于词频的传统信息检索
3. **Rerank重排**：使用BGE-Reranker对检索结果重新排序

## 文档分块策略

- **语义分块**：基于Markdown标题结构进行智能分块
- **动态重叠**：相邻块之间保持10%-20%的重叠
- **最大长度**：每个块最大1000字符

## 测试

项目包含自动化测试套件：

```bash
cd tests
python -m pytest
```

## Docker部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

---

**注意**：使用前请确保已配置好所有必要的API密钥和环境变量。
