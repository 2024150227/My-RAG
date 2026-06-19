# MY-RAG · 企业级 RAG 知识库系统

[![CI](https://github.com/2024150227/My-RAG/actions/workflows/ci.yml/badge.svg)](https://github.com/2024150227/My-RAG/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/2024150227/My-RAG)](https://github.com/2024150227/My-RAG/releases)

基于 **LangChain + ChromaDB** 的企业级 RAG 系统，支持多用户私有知识库、混合检索、多 LLM Provider（本地 Ollama / 火山方舟 Ark / 硅基流动）、链路 Hooks 与一键云部署。

> 🌐 **线上体验**：[http://47.106.186.17:7860](http://47.106.186.17:7860)（账号 `admin` / 密码 `admin@2026`）

---

## ✨ 功能特性

### 知识库与检索
- 📄 **多格式文档**：Markdown / PDF / Word(.docx) / TXT / Excel
- 🖼️ **图文混合检索**：上传 PDF/Word 时自动抽取内嵌图片（PyMuPDF + python-docx），按 md5 去重存盘；检索时随相关 chunk 一并返回，前端 Gradio 画廊实时渲染相关图片
- ✂️ **语义分块**：基于 Markdown 标题结构的智能切分，块间动态重叠
- 🔍 **混合检索**：向量检索（BGE-M3）+ BM25，结果走 BGE-Reranker-v2-m3 重排
- 👤 **多用户隔离**：每个账号拥有独立的私有知识库（ChromaDB metadata 区分），私有图片走 token 鉴权静态路由

### 大语言模型
- 🔀 **多 Provider 可切换**：LLM 走 `LLM_PROVIDER` 三选一（本地 Ollama / 火山方舟 Doubao / 硅基流动），Embedding 走 `EMBED_PROVIDER` 双选一（火山方舟 Doubao / 硅基流动 BGE-M3），rerank 固定走硅基流动 BGE-Reranker-v2-m3；切换 Embedding 需清库重新入库
- 📡 **流式输出（SSE）**：`/query/stream` 接口逐 token 返回，前端 Gradio 像 ChatGPT 一样实时打字效果
- 🎯 **链路 Hooks**：`before_agent` / `before_model` / `wrap_model_call` / `after_model` / `after_agent` 五段切片，覆盖鉴权、Prompt 拼装、缓存重试熔断、格式修正、持久化全链路
- 🔬 **节点级耗时埋点**：基于 `contextvars` 把 8 个关键节点（embedding / 向量检索 / BM25 / 合并 / rerank / 历史 / 缓存 / LLM）的耗时按 session_id 汇总；前端 Gradio 实时渲染 HTML 瀑布图，瓶颈节点红色高亮
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
| 嵌入 | 火山方舟 Doubao Embedding Large *或* BAAI/bge-m3（硅基流动） |
| 重排 | BAAI/bge-reranker-v2-m3（硅基流动 API） |
| LLM | Ollama（本地 Qwen / DeepSeek 等）*或* 火山方舟（Doubao Seed / DeepSeek V3）*或* SiliconFlow（Qwen2.5-7B-Instruct） |
| 缓存 / 会话 | Redis 5.0 |
| 账号 / 历史 | MySQL 8.0 + SQLAlchemy 2.0 |
| 文档 | LangChain 0.1 + PyPDF + **PyMuPDF** + openpyxl + python-docx |

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
│       ├── llm_service.py         # ★ 三 Provider（ollama / ark / siliconflow），OpenAI 兼容协议抽象
│       ├── embedding_service.py   # ★ 双 Provider（ark / siliconflow）
│       ├── rerank_service.py      # 调硅基流动 rerank
│       ├── retrieval_engine.py    # 混合检索（向量 + BM25），透传 metadata + 5 段 time_block
│       ├── chroma_service.py      # ChromaDB 客户端
│       ├── document_processor.py  # 文档分块 + 图片抽取（PyMuPDF / python-docx）
│       ├── user_service.py        # 注册 / 登录 / token 管理
│       └── hooks_manager.py       # 链路 hooks（5 段切片 + 节点级耗时汇总）
├── app/utils/
│   ├── logger.py                  # 全局 logger
│   └── timer.py                   # ★ 节点耗时计时器（contextvars + time_block）
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
- Ollama（本地 LLM 模式需要）*或* 火山方舟 API Key（推荐，LLM + Embedding）*或* 硅基流动 API Key（Rerank 必选，LLM/Embedding 可选）

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
export ARK_API_KEY=ark-xxx                          # 火山方舟（LLM + Embedding）
export SILICONFLOW_API_KEY=sk-xxx                   # 硅基流动（Rerank）
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
| `LLM_PROVIDER` | LLM 提供方：`ark` / `ollama` / `siliconflow` | `ark` |
| `EMBED_PROVIDER` | Embedding 提供方：`ark` / `siliconflow`（切换需清库） | `ark` |
| `ARK_API_KEY` | 火山方舟 Key（LLM + Embedding） | 必填 |
| `ARK_BASE_URL` | 火山方舟 API 基址（OpenAI 兼容 /api/v3） | `https://ark.cn-beijing.volces.com/api/v3` |
| `ARK_LLM_MODEL` | 火山方舟 LLM 模型 | `doubao-1-5-pro-32k-250115` |
| `ARK_EMBED_MODEL` | 火山方舟 Embedding 模型 | `doubao-embedding-large-text-250515` |
| `OLLAMA_MODEL` | 本地 Ollama 模型名 | `qwen:latest` |
| `SILICONFLOW_API_KEY` | 硅基流动 Key（Rerank 必用，LLM/Embedding 可选） | 必填 |
| `SILICONFLOW_LLM_MODEL` | 硅基流动 LLM 模型 | `Qwen/Qwen2.5-7B-Instruct` |
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
| `POST` | `/upload` | 上传文档（按用户隔离，同名先返回 `409` 让前端确认覆盖；自动抽取内嵌图片） |
| `POST` | `/query` | 单次问答（一次性返回完整答案，含相关图片 URL + 节点级 `node_timings`） |
| `POST` | `/query/stream` | **流式问答**（SSE，逐 token 推送，前端实时打字效果，meta 帧含图片 URL，done 帧含 `node_timings`） |
| `POST` | `/query/batch` | 批量问答 |
| `GET` | `/stats` | 知识库统计 |
| `DELETE` | `/clear` | 清空当前用户知识库 |
| `GET` | `/files/{user_id}/{path}` | 私有图片下载（token 鉴权 + 防越权 + 防路径穿越） |
| `GET` | `/execution-stats/{session_id}` | 查询会话级链路耗时（hooks_timing + node_timings） |

### 会话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/session/new` | 新建会话 |
| `GET` | `/session/history/{session_id}` | 查询会话历史 |

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

> 💡 SSE 帧类型：`meta`（检索上下文 + 图片 URL）→ `token`（逐 token 增量）→ `fixed`（after-model 修正）→ `done`（结尾统计）；错误用 `error` 帧返回。

---

## 🖼️ 图文混合检索

PDF / Word 文档上传时，系统会自动抽取内嵌图片随相关 chunk 一起返回。

### 链路

```
上传 PDF/Word
   ↓
PyMuPDF 抽 PDF 图 / python-docx 抽 Word 图
   ↓
md5 命名去重 + 过滤 < 2KB 的小图标
   ↓
存盘到 uploads/<user_id>/_images/<md5前12位>/
   ↓
图片相对路径以逗号串形式写进 ChromaDB chunk 的 metadata.images

────────────────────（查询时）────────────────────

hybrid_search 透传 metadata
   ↓
路由层 _collect_image_urls 跨 chunk 去重
   ↓
SSE meta 帧返回相对路径列表
   ↓
前端拼成 /files/<user_id>/...?token=xxx
   ↓
gr.Gallery 渲染（浏览器 <img> 通过 /files 路由拉图）
   ↓
后端三重校验：token 有效 + URL user_id 与 token user_id 匹配 + 路径白名单
```

### 关键设计取舍

| 选择 | 原因 |
| --- | --- |
| 用 PyMuPDF 而非 pypdf 抽图 | pypdf 抽图 API 残废；PyMuPDF 是工业标准，按 xref 抽 |
| md5 命名 + < 2KB 过滤 | 同图天然去重；过滤图标分隔线避免画廊污染 |
| 图存盘 + metadata 存路径 | ChromaDB 不擅长大对象；磁盘 + 路径串方案干净 |
| 同一文档所有 chunk 共享全部图 | 第一版简化；可后续做 chunk-图位置精细对齐 |
| **query string 鉴权**而非 header | `<img src="...">` 标签发不了自定义 header |

> 仅支持 OOXML 格式（.docx，Word 2007+）；旧版二进制 .doc 需先用 Word/LibreOffice 另存为 .docx。

---

## 🔬 链路可观测性

整个 RAG 链路从黑盒拆成 8 个可观测节点，每次问答都自动统计耗时，前端实时渲染瀑布图。

### 节点清单

| # | 节点 | 干什么 | 典型耗时 |
| --- | --- | --- | --- |
| 1 | `query_embedding` | query 向量化（Ark Doubao / BGE-M3） | 30~80ms |
| 2 | `vector_search` | ChromaDB 向量近邻搜索 | 50~300ms |
| 3 | `bm25_search` | 关键词召回（与向量检索并行） | 20~80ms |
| 4 | `merge_dedup` | 双路结果合并 + 去重 | 1~5ms |
| 5 | `rerank` | BGE-Reranker-v2-m3 精排 top_k | 500~1500ms |
| 6 | `history_fetch` | 从 Redis 拉多轮对话历史 | 5~20ms |
| 7 | `llm_cache_lookup` | 查 LLM 输出缓存（命中跳过推理） | 1~5ms |
| 8 | `llm_inference` | 真正调 LLM 出答案（流式 / 同步） | 2000~8000ms |

### 实现要点

- **`app/utils/timer.py`** 提供 `set_session(sid)` + `time_block(name)` 两个原语，基于 `contextvars` 把 session_id 绑到当前协程上下文，services 层不用感知"会话"概念
- `before_agent` hook 入口绑定一次；SSE `event_generator` 入口再绑定一次（`StreamingResponse` 会切到新协程上下文）
- 数据存到 `rag_hooks.execution_stats[sid]["node_timings"][name]`，类型是 list（同节点多次调用累加）
- 单位**统一为秒**，与 `hooks_timing` 一致
- `after_agent` 多打一行 `[perf]` 日志，例：

  ```
  [perf] sid=a7f3e1c2 emb=0.045s vec=0.182s bm25=0.038s merge=0.001s
         rerank=0.812s hist=0.009s cache=0.002s llm=3.050s total=4.139s
  ```

- SSE `done` 帧与 `/query` 同步接口都返回 `node_timings` 字段
- 前端 Gradio 用纯 HTML/CSS 渲染瀑布图（不引 matplotlib），瓶颈节点 LLM 推理用红色高亮

### 设计取舍

| 选择 | 原因 |
| --- | --- |
| `contextvars` 而非显式传 session_id | services 层不该感知"会话"概念；`contextvars` 是 Python 异步友好的标准方案 |
| 存 list 而非单值 | 一次请求里 embedding / LLM 可能多次调用（多轮、多 chunk），存 list 才能算总和 / 平均 |
| 不新增 hook 而是装饰节点 | 现有 5 个 hook 是**生命周期切片**，节点埋点是**性能观测**，两件事别混 |
| 不引入 OpenTelemetry | 单机部署用不上分布式追踪；将来真要上 Jaeger 再换 |

---

## 🔍 检索策略

```
用户问题
   ↓
[before_agent hook] 鉴权 / 起 stats / 绑定 contextvar
   ↓
hybrid_search 内 5 段 time_block：
   query_embedding → vector_search ┐
                                   ├→ merge_dedup → rerank
                     bm25_search ──┘
   ↓
[before_model hook] history_fetch + Prompt 拼装 + 上下文裁剪 + 敏感词过滤
   ↓
[wrap_model_call hook] llm_cache_lookup → 未命中走 llm_inference（重试 / 熔断）
   ↓
[after_model hook] 输出格式修正
   ↓
[after_agent hook] MySQL 落库 + Redis 摘要 + [perf] 节点级耗时汇总日志
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
| **v1.2.4** | LLM + Embedding 迁移至火山方舟 Ark：新增 Ark provider（LLM 三选一 / Embedding 双选一），OpenAI 兼容协议抽象统一方法、同步流式均覆盖；Doubao Seed 1.6 / Doubao 1.5 Pro 可选；`config.py` 新增 `ARK_API_KEY` / `EMBED_PROVIDER` 等配置项；`deploy/install-app.sh` .env 模板适配双 Key；rerank 保留硅基流动；注意换 embedding = 向量维度变化，必须清空 ChromaDB 重新入库 |
| **v1.2.3** | 新增节点级链路耗时埋点 + Gradio 瀑布图可视化：基于 `contextvars` 把 8 个关键节点（embedding / vector / BM25 / merge / rerank / history / cache / LLM）的耗时按 session_id 汇总；`hybrid_search` 拆出 5 段 `time_block`；SSE done 帧 + `/query` 同步接口返回 `node_timings`；前端 Gradio HTML 瀑布图实时渲染，瓶颈节点红色高亮；`after_agent` 多打一行 `[perf]` 节点级汇总日志，单位统一为秒 |
| **v1.2.2** | 新增图文混合检索：上传 PDF/Word 自动抽内嵌图（PyMuPDF + python-docx），md5 去重存盘；检索时随 chunk 返回，前端 Gradio 画廊实时渲染；新增 `/files/{user_id}/{path}` 私有图片路由（token 鉴权 + 防越权 + 防路径穿越）；`retrieval_engine.hybrid_search` 透传 metadata |
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

> **Tip**：踩坑记录与最佳实践详见 [`deploy/README.md`](deploy/README.md) 和 [项目作者的博客](https://2024150227.github.io/)（含 SSE 中文乱码修复、1G 内存云部署、工程化踩坑实录等系列文章）。
