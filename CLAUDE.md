# MY-RAG 项目说明（Claude 工作指南）

> 本文件让 Claude Code 在每次会话开始时获得项目上下文。代码风格、部署架构、踩过的坑都在这里。**新会话开始时请遵守本文件的约定**。

---

## 🎯 项目简介

**MY-RAG** 是一个基于 **LangChain + ChromaDB + LLM** 的企业级 RAG 知识库系统：

- **后端**：FastAPI（端口 8000）
- **前端**：Gradio（端口 7860）
- **向量库**：ChromaDB（本地文件，路径 `chromadb_data/`）
- **缓存 / 会话**：Redis
- **账号体系**：MySQL（用户、登录令牌、聊天历史）
- **嵌入 / 重排**：硅基流动 API（BGE-M3 / BGE-Reranker-v2-m3）
- **LLM**：双 provider，可切换
  - `LLM_PROVIDER=ollama`（默认）→ 本地 Ollama
  - `LLM_PROVIDER=siliconflow` → 云端硅基流动 chat API

---

## 📁 关键目录与文件

```
MY-RAG/
├── app/
│   ├── api/routes.py              # 所有 HTTP 路由（注册/登录/查询/上传等）
│   ├── config.py                  # ★ 所有环境变量统一在这读取
│   ├── main.py                    # FastAPI app 入口
│   ├── db/
│   │   ├── redis_client.py        # Redis 封装（账号、会话）
│   │   └── mysql_client.py        # MySQL 封装（SQLAlchemy）
│   ├── frontend/gradio_app.py     # Gradio UI，末尾根据 .env 决定 basic auth
│   ├── services/                  # 业务核心
│   │   ├── llm_service.py         # ★ 双 provider 实现（ollama / siliconflow）
│   │   ├── embedding_service.py   # 调硅基流动 embedding
│   │   ├── rerank_service.py      # 调硅基流动 rerank
│   │   ├── retrieval_engine.py    # 混合检索 (向量 + BM25)
│   │   ├── chroma_service.py      # ChromaDB 客户端
│   │   ├── document_processor.py  # 文档分块（基于 Markdown 标题）
│   │   ├── user_service.py        # 注册/登录/token 管理
│   │   └── hooks_manager.py       # 链路 hooks（性能埋点）
│   └── utils/logger.py            # 全局 logger
├── deploy/                        # 云服务器部署脚本（Ubuntu）
│   ├── server-setup.sh            # 装 Redis/MySQL/Python，配 swap、防火墙
│   ├── install-app.sh             # venv + 写 .env + systemd
│   └── README.md                  # 部署说明（看这个就够）
├── scripts/
│   ├── start_api.py               # 启动 FastAPI
│   └── init_knowledge.py          # 批量入库脚本
├── start.bat / stop.bat           # Windows 本地一键启停
├── docker-compose.yml             # 本地全容器开发模式（按需）
└── requirements.txt
```

---

## 🛠️ 三种部署模式

每种模式 **完全独立**，不要混用。

### 1. 本地开发（Windows）—— 当前主力

```bash
# 中间件用 Docker，应用走 venv
docker compose up -d redis mysql
venv\Scripts\python.exe scripts\start_api.py
venv\Scripts\python.exe app\frontend\gradio_app.py
# 或者一键启动
start.bat
```

### 2. 全容器开发（少用）

```bash
docker compose up -d   # api / gradio 也容器化
```

### 3. 云服务器部署（生产）

服务器 `47.106.186.17`，Ubuntu 22.04，**1G 内存**：

```bash
sudo bash deploy/server-setup.sh                    # 装中间件
export SILICONFLOW_API_KEY=sk-xxx
export GRADIO_AUTH_PASSWORD='xxx'
sudo -E bash deploy/install-app.sh                  # 部署应用
```

详见 `deploy/README.md`。

---

## ⚙️ 配置规范（很重要）

### 所有环境变量从 `app/config.py` 的 `Settings` 读取

新增配置项必须**三处同步**，否则部署会出问题：

1. `app/config.py` — 加 `os.getenv("XXX", "默认值")`
2. `.env.example`（如有）/ 项目根 `.env` — 加示例
3. `deploy/install-app.sh` 里的 `.env` 模板 — 加同名变量

### 关键配置项

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` / `siliconflow` | `ollama` |
| `OLLAMA_MODEL` | 本地模型名 | `qwen:latest` |
| `SILICONFLOW_LLM_MODEL` | 云端模型 | `Qwen/Qwen2.5-7B-Instruct` |
| `SILICONFLOW_API_KEY` | 硅基流动 Key（embedding / rerank / LLM 共用） | 必填 |
| `GRADIO_AUTH_USER/PASSWORD` | Gradio basic auth | 空 = 不启用 |
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | MySQL 连接 | 本地 / 容器不同 |
| `REDIS_HOST/PORT` | Redis 连接 | 本地 / 容器不同 |

---

## 📝 代码约定

### 风格

- 全部用**中文注释**和日志
- API 路由集中在 `app/api/routes.py`，**不要分散到多个文件**
- 业务逻辑放在 `app/services/<name>_service.py`，每个服务一个 class，文件末尾导出单例 `xxx_service = XxxService()`
- 跨服务调用通过单例，不要再 `XxxService()` 实例化

### 错误处理

- 服务层捕获异常返回 `{"success": False, "message": ...}` 风格的字典或字符串
- 路由层包装成 `{"code": 200/400/...}` 的统一格式（参考现有 `routes.py`）
- LLM / API 调用必须有 timeout，并 logger.error 打印详细错误

### 新增依赖

- 加到 `requirements.txt`，**钉死版本号**
- 重启脚本需要 `pip install -r requirements.txt`，重新部署 `bash deploy/install-app.sh`

---

## 🚦 常见任务怎么做

### 新增一个 API 接口

1. 在 `app/api/routes.py` 的相应位置加 `@router.post("/xxx")`
2. 用 Pydantic 定义 Request/Response 模型
3. 调用对应的 `app/services/xxx_service.py` 方法
4. 返回统一 `{"code", "message", "data"}` 格式

### 修改 LLM 行为

- **只改 `app/services/llm_service.py`**
- 双 provider 都要测：本地 Ollama + 云端 SiliconFlow
- prompt 改动放 `SYSTEM_PROMPT` 常量

### 新增前端控件

- 改 `app/frontend/gradio_app.py`
- 函数命名：操作动词开头（`query_api` / `register_user` / `upload_file`）
- 错误信息用 emoji 前缀：✅ 成功 / ❌ 失败 / ⚠️ 警告

---

## ❌ 不要做的事

- **不要把 `.env` 提交到 git**（已被 `.gitignore` 排除，确认你新加的密钥也用 env 而非硬编码）
- **不要硬编码 API Key、密码、IP**——一律 `os.getenv`
- **不要在 1G 内存的云服务器上启用 Ollama**——必须用 `LLM_PROVIDER=siliconflow`
- **不要直接修改 `chromadb_data/` 和 `uploads/` 里的文件**——是运行时数据
- **不要用容器版 Redis + 本地 venv 应用混搭跑生产**（配置会不一致），开发倒是可以
- **不要把 `MYSQL_PASSWORD=password` 这种弱密码用到生产**

---

## 🧪 测试

```bash
# 单元测试（如果有）
venv\Scripts\python.exe -m pytest tests/

# 端到端验证（最常用）
# 1. 起服务（start.bat 或 systemctl restart my-rag-api）
# 2. 测注册登录
curl -X POST http://localhost:8000/register -H "Content-Type: application/json" -d "{\"username\":\"t\",\"password\":\"123456\"}"
curl -X POST http://localhost:8000/login    -H "Content-Type: application/json" -d "{\"username\":\"t\",\"password\":\"123456\"}"
# 3. 测问答
curl -X POST http://localhost:8000/query    -H "Content-Type: application/json" -d "{\"query\":\"你好\",\"top_k\":3}"
```

---

## 📦 git / commit 规范

- commit message 用**中文**，遵循 Conventional Commits：
  - `feat: 新增 xxx`
  - `fix: 修复 xxx`
  - `chore: 升级依赖 / CI 调整`
  - `docs: 更新文档`
  - `refactor: 重构 xxx`
- 大改动开 PR，不要直接 push main
- 发布版本打 tag `v1.x.x`，配 GitHub Release

---

## 🐛 已知问题 / 历史踩坑（避免重复犯）

1. **Windows cmd 中文乱码**：bat 脚本必须 `chcp 65001 >nul` 在前；某些环境 `bind 'set enable-bracketed-paste off'` 可避免粘贴时被加缩进
2. **`Empty value for 'table_open_cache'`**：用 here-doc 写 MySQL 配置时易因终端缩进损坏，**改用 `{ echo ...; } > file` 单行模式**
3. **登录"用户不存在"**：账号体系实际存在 Redis（不是 MySQL），Redis 挂了注册会假成功
4. **GPU OOM**：本机 4G 显存跑不动 qwen:latest，要么换 qwen3.5:latest（也吃力），要么走云端 API
5. **MySQL 容器和本地服务冲突**：6379 / 3307 端口被本地 Redis/MySQL 占住时容器起不来；先 `taskkill` 或 `Stop-Service`
6. **Ollama 在 1G 服务器上**：连最小模型也跑不动，**直接用 SiliconFlow**

---

## 🔑 服务器凭据（仅供 Claude 参考，**不要 commit 真实生产密码**）

> 如果你看到的是开源仓库，这些是**示例占位**——实际密码看私有 memory 或运维笔记。

- 服务器 IP：`47.106.186.17`（Ubuntu 22.04，1G）
- MySQL：`root / RagRoot@2026`、`rag / RagApp@2026`、库 `rag_db`
- Gradio 默认账号：`admin / admin@2026`
- 部署目录：`/opt/my-rag`
- systemd 服务：`my-rag-api`、`my-rag-gradio`

---

## 🤖 Claude 协作约定

- **回答用中文**
- **重点放在最前**，避免冗长前置铺垫
- **改代码前先 Read，禁止凭记忆修改**
- **大动作（部署、删数据、推 git）必须先确认**
- **命令行交互**遇到中文乱码时主动提示用户用 PowerShell 或 SSH 客户端的 UTF-8 模式
- 用户母语是中文，但欢迎在变量名 / 文件名上用英文以保证兼容性
