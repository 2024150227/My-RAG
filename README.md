# MY-RAG · 企业级 RAG 知识库系统

[![CI](https://github.com/2024150227/My-RAG/actions/workflows/ci.yml/badge.svg)](https://github.com/2024150227/My-RAG/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/2024150227/My-RAG)](https://github.com/2024150227/My-RAG/releases)

基于 **LangChain + ChromaDB** 的企业级 RAG 系统，支持多用户私有知识库、混合检索、双 LLM Provider（本地 Ollama / 云端硅基流动）、链路 Hooks 与一键云部署。

> 🌐 **线上体验**：[http://47.106.186.17:7860](http://47.106.186.17:7860)（账号 `admin` / 密码 `admin@2026`）

---

## ✨ 功能特性

### 知识库与检索
- 📄 **多格式文档**：Markdown / PDF / Word(.docx) / TXT / Excel
- ✂️ **语义分块**：基于 Markdown 标题结构的智能切分，块间动态重叠
- 🔍 **混合检索**：向量检索（BGE-M3）+ BM25，结果走 BGE-Reranker-v2-m3 重排
- 👤 **多用户隔离**：每个账号拥有独立的私有知识库（ChromaDB metadata 区分）

### 大语言模型
- 🔀 **双 Provider 切换**：通过 `LLM_PROVIDER` 环境变量在本地 Ollama 与硅基流动云端 API 间无缝切换
- 📡 **流式输出（SSE）**：`/query/stream` 接口逐 token 返回，前端 Gradio 像 ChatGPT 一样实时打字效果
- 🎯 **链路 Hooks**：`before_retrieval` / `before_model` / `after_model` 三段切片，便于埋点 / 限流 / 内容审计
- ⚡ **上下文裁剪**：超长 prompt 自动按段落边界回退到 token 上限内
- 💬 **多轮对话**：基于 Redis 的会话上下文 + MySQL 持久化历史

### 工程与部署
- 🔐 **账号体系**：注册 / 登录 / Token 校验 / 会话隔离
- 🛡️ **Gradio basic auth**：前端可选启用账号密码保护，避免公网裸奔
- 📂 **上传重名检测**：同名文档先弹窗让用户确认覆盖 or 取消，避免误操作
- 🐳 **三种部署模式**：本地开发 / 全 Docker / 云服务器原生（含 1G 内存调优脚本）
- 📊 **systemd 守护**：FastAPI / Gradio 自动拉起、journalctl 看日志

---

## 🛠️ 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | FastAPI 0.110 + Uvicorn |
| 前端 | Gradio 4.21（带可选 basic auth） |
| 向量库 | ChromaDB 0.4.24 |
| 嵌入 / 重排 | BAAI/bge-m3 + BAAI/bge-reranker-v2-m3（硅基流动 API） |
| LLM | Ollama（本地 Qwen / DeepSeek 等） *或* SiliconFlow（Qwen2.5-7B-Instruct 等） |
| 缓存 / 会话 | Redis 5.0 |
| 账号 / 历史 | MySQL 8.0 + SQLAlchemy 2.0 |
| 文档 | LangChain 0.1 + PyPDF + openpyxl + python-docx |

---

## 📁 项目结构

```
MY-RAG/
├── app/
│   ├── api/routes.py              # 所有 HTTP 路由（注册/登录/查询/上传等）
│   ├── config.py                  # 环境变量统一入口
│   ├── main.py                    # FastAPI app 入口
│   ├── db/
│   │   ├── redis_client.py        # Redis（账号 / 会话）
│   │   └── mysql_client.py        # MySQL（用户、历史）
│   ├── frontend/gradio_app.py     # Gradio UI（含 basic auth）
│   └── services/                  # 业务核心
│       ├── llm_service.py         # ★ 双 Provider 实现（ollama / siliconflow）
│       ├── embedding_service.py   # 调硅基流动 embedding
│       ├── rerank_service.py      # 调硅基流动 rerank
│       ├── retrieval_engine.py    # 混合检索（向量 + BM25）
│       ├── chroma_service.py      # ChromaDB 客户端
│       ├── document_processor.py  # 文档分块（基于 Markdown 标题）
│       ├── user_service.py        # 注册 / 登录 / token 管理
│       └── hooks_manager.py       # 链路 hooks（性能埋点、上下文裁剪）
├── deploy/                        # 云服务器部署脚本（Ubuntu）
│   ├── server-setup.sh            # 装 Redis/MySQL/Python，配 swap、防火墙
│   ├── install-app.sh             # venv + 写 .env + systemd
│   └── README.md                  # 完整部署说明
├── scripts/
│   ├── start_api.py               # 启动 FastAPI
│   ├── init_knowledge.py          # 批量入库脚本
│   └── debug_sse.py               # SSE 流式接口字节级调试工具
├── start.bat / stop.bat           # Windows 一键启停（仅本地开发）
├── docker-compose.yml             # 全容器开发模式
└── requirements.txt
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11
- Redis（本地或容器）
- MySQL 8（本地或容器）
- Ollama（本地 LLM 模式需要） *或* 硅基流动 API Key（云端 LLM 模式）

### 三种部署模式

#### 1. 本地开发（推荐）

```bash
# 中间件用 Docker，应用走 venv
docker compose up -d redis mysql

python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

cp .env.example .env           # 编辑 API Key 等参数
python scripts/start_api.py    # 端口 8000
python app/frontend/gradio_app.py  # 端口 7860

# Windows 一键启停
start.bat / stop.bat
```

#### 2. 全 Docker 开发

```bash
docker compose up -d
```

#### 3. 云服务器部署（生产）

```bash
# 在服务器上
sudo bash deploy/server-setup.sh                    # 装 Redis/MySQL/Python
export SILICONFLOW_API_KEY=sk-xxx
export GRADIO_AUTH_PASSWORD='your-password'
sudo -E bash deploy/install-app.sh                  # 部署应用 + systemd
```

详见 [`deploy/README.md`](deploy/README.md)（含 1G 内存机器调优、踩坑记录）。

---

## ⚙️ 配置说明

所有配置统一在 `app/config.py` 读取，**新增项需要 `app/config.py` + `.env` + `deploy/install-app.sh` 三处同步**。

### 关键配置项

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LLM_PROVIDER` | LLM 提供方：`ollama` / `siliconflow` | `ollama` |
| `OLLAMA_MODEL` | 本地模型名 | `qwen:latest` |
| `SILICONFLOW_LLM_MODEL` | 云端模型 | `Qwen/Qwen2.5-7B-Instruct` |
| `SILICONFLOW_API_KEY` | 硅基流动 Key（embed / rerank / LLM 共用） | 必填 |
| `GRADIO_AUTH_USER` / `GRADIO_AUTH_PASSWORD` | 前端 basic auth | 空 = 不启用 |
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | MySQL 连接 | 见 `.env.example` |
| `REDIS_HOST/PORT` | Redis 连接 | `localhost:6379` |
| `TEMPERATURE` / `TOP_K` / `MAX_TOKENS` | LLM 推理参数 | `0.4` / `3` / `500` |

---

## 📡 API 接口

### 账号体系

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/register` | 注册（返回 user_id） |
| `POST` | `/login` | 登录（返回 token） |
| `POST` | `/logout` | 登出（带 `token` header） |
| `GET` | `/verify` | 校验 token |

### 知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/upload` | 上传文档（按用户隔离，同名先返回 `409` 让前端确认覆盖） |
| `POST` | `/query` | 单次问答（一次性返回完整答案） |
| `POST` | `/query/stream` | **流式问答**（SSE，逐 token 推送，前端实时打字效果） |
| `POST` | `/query/batch` | 批量问答 |
| `GET` | `/stats` | 知识库统计 |
| `DELETE` | `/clear` | 清空当前用户知识库 |

### 会话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/session/new` | 新建会话 |
| `GET` | `/session/history/{session_id}` | 查询会话历史 |
| `GET` | `/execution-stats/{session_id}` | 查询链路耗时统计 |

### 调用示例

```python
import requests

# 1. 登录拿 token
r = requests.post("http://localhost:8000/login",
                  json={"username": "alice", "password": "123456"})
token = r.json()["data"]["token"]

# 2. 上传文档
with open("doc.pdf", "rb") as f:
    requests.post("http://localhost:8000/upload",
                  files={"file": f},
                  headers={"token": token})

# 3. 问答
r = requests.post("http://localhost:8000/query",
                  json={"query": "DSW 计费方式是什么？", "top_k": 3},
                  headers={"token": token})
print(r.json()["data"]["answer"])

# 4. 流式问答（SSE）
import json
with requests.post("http://localhost:8000/query/stream",
                   json={"query": "DSW 计费方式是什么？"},
                   headers={"token": token},
                   stream=True) as resp:
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        frame = json.loads(line[5:])
        if frame["type"] == "token":
            print(frame["content"], end="", flush=True)
        elif frame["type"] == "done":
            break
```

> 💡 SSE 帧类型：`meta`（检索上下文）→ `token`（逐 token 增量）→ `fixed`（after-model 修正）→ `done`（结尾统计）；错误用 `error` 帧返回。

---

## 🔍 检索策略

```
用户问题
   ↓
[before_retrieval hook] 性能埋点 / 关键词改写
   ↓
向量检索（BGE-M3）   +   BM25 检索      ← 并行召回
   ↓
结果合并 / 去重
   ↓
BGE-Reranker-v2-m3 重排                 ← 取 top_k
   ↓
[before_model hook] Prompt 拼装 / 上下文裁剪 / 敏感词过滤
   ↓
LLM 推理（Ollama 或 SiliconFlow）
   ↓
[after_model hook] 性能统计 / 历史落库
   ↓
返回答案
```

文档分块策略：

- **语义分块**：基于 Markdown 标题层级
- **动态重叠**：相邻 chunk 保持 10%-20% 重叠
- **最大长度**：单 chunk ≤ 1000 字符

---

## 🔐 安全建议

1. **不要把 `.env` 提交到 git**（已在 `.gitignore` 中）
2. **生产环境改默认密码**：MySQL `RagApp@2026` / Gradio `admin@2026` 仅作示例
3. **Gradio 公网部署务必启用 `GRADIO_AUTH_*`** 或加 Nginx + basic auth
4. **token 默认 24 小时过期**，长期会话要做 refresh
5. **API Key 严禁硬编码**，一律走 `os.getenv`

---

## 🧪 测试

```bash
# 端到端验证（最常用）
curl -X POST http://localhost:8000/register \
     -H "Content-Type: application/json" \
     -d '{"username":"t","password":"123456"}'

curl -X POST http://localhost:8000/login \
     -H "Content-Type: application/json" \
     -d '{"username":"t","password":"123456"}'

curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -H "token: <上一步返回的 token>" \
     -d '{"query":"你好","top_k":3}'
```

---

## 🗒️ 版本历史

| 版本 | 主要变更 |
| --- | --- |
| **v1.2.1** | 新增 `/query/stream` 流式问答接口（SSE 逐 token 推送）；前端 Gradio 实时打字效果；上传重名检测与覆盖确认；敏感词过滤只查用户原始 query；修复 SSE 中文乱码（增量 UTF-8 解码 + charset 头）；Windows 启动加 `-X utf8` |
| **v1.2.0** | README 全面更新；docs/部署文档完善 |
| **v1.1.0** | 双 LLM Provider；Gradio basic auth；云服务器部署套件；多用户私有知识库；上下文裁剪优化；MySQL URL 编码 fix |
| **v1.0.0** | 初版：FastAPI + Gradio + ChromaDB + 混合检索 + Ollama |

完整发布记录见 [Releases](https://github.com/2024150227/My-RAG/releases)。

---

## 📜 许可证

[MIT License](LICENSE)

## 🤝 贡献

欢迎提交 Issue 与 Pull Request！开发约定参见 [CLAUDE.md](CLAUDE.md)。

---

> **Tip**：踩坑记录与最佳实践详见 [`deploy/README.md`](deploy/README.md) 和 [项目作者的博客](https://2024150227.github.io/)（建设中）。
