#!/usr/bin/env bash
# =============================================================================
#  MY-RAG 应用部署脚本（1G 内存 / LLM + Embedding 走火山方舟，rerank 走硅基流动）
#  约定：
#    - 项目代码已经上传到 /opt/my-rag
#    - 服务器环境已经用 server-setup.sh 装好
#  使用：
#      export ARK_API_KEY=ark-xxx                 # 火山方舟（LLM + Embedding）
#      export SILICONFLOW_API_KEY=sk-xxx          # 仅用于 rerank
#      export GRADIO_AUTH_PASSWORD='你的密码'
#      sudo -E bash /opt/my-rag/deploy/install-app.sh
# =============================================================================

set -e

# -------- 可调参数（要和 server-setup.sh 保持一致） --------
APP_DIR="${APP_DIR:-/opt/my-rag}"
APP_USER="${APP_USER:-rag}"
MYSQL_APP_USER="${MYSQL_APP_USER:-rag}"
MYSQL_APP_PASSWORD="${MYSQL_APP_PASSWORD:-RagApp@2026}"
MYSQL_DATABASE="${MYSQL_DATABASE:-rag_db}"

# 火山方舟（LLM + Embedding）
ARK_API_KEY="${ARK_API_KEY:?需要设置 ARK_API_KEY 环境变量}"
ARK_BASE_URL="${ARK_BASE_URL:-https://ark.cn-beijing.volces.com/api/v3}"
ARK_LLM_MODEL="${ARK_LLM_MODEL:-doubao-1-5-pro-32k-250115}"
ARK_EMBED_MODEL="${ARK_EMBED_MODEL:-doubao-embedding-large-text-240915}"

# 硅基流动（仅 rerank）
SILICONFLOW_API_KEY="${SILICONFLOW_API_KEY:?需要设置 SILICONFLOW_API_KEY 环境变量（rerank 用）}"
SILICONFLOW_LLM_MODEL="${SILICONFLOW_LLM_MODEL:-Qwen/Qwen2.5-7B-Instruct}"

GRADIO_AUTH_USER="${GRADIO_AUTH_USER:-admin}"
GRADIO_AUTH_PASSWORD="${GRADIO_AUTH_PASSWORD:-admin@2026}"
PUBLIC_IP="${PUBLIC_IP:-47.106.186.17}"
# -----------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    echo "请用 root 或 sudo 运行: sudo bash $0"
    exit 1
fi

if [[ ! -f "$APP_DIR/requirements.txt" ]]; then
    echo "找不到 $APP_DIR/requirements.txt，请确认代码已上传到 $APP_DIR"
    exit 1
fi

echo "============================================================"
echo "  [1/5] 创建系统用户 & 目录权限"
echo "============================================================"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "============================================================"
echo "  [2/5] 创建 Python venv & 装依赖（1G 机器编译慢，请耐心）"
echo "============================================================"
sudo -u "$APP_USER" bash -lc "
    cd '$APP_DIR'
    python3.11 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install --no-cache-dir -r requirements.txt
"

echo "============================================================"
echo "  [3/5] 写入 .env"
echo "============================================================"
cat > "$APP_DIR/.env" <<EOF
# === 硅基流动 API（仅 rerank 仍用）===
SILICONFLOW_API_KEY=${SILICONFLOW_API_KEY}
SILICONFLOW_EMBED_URL=https://api.siliconflow.cn/v1/embeddings
SILICONFLOW_RERANK_URL=https://api.siliconflow.cn/v1/rerank
SILICONFLOW_LLM_URL=https://api.siliconflow.cn/v1/chat/completions
SILICONFLOW_LLM_MODEL=${SILICONFLOW_LLM_MODEL}

# === 火山方舟 API（LLM + Embedding）===
# 注意：API base 用 /api/v3（OpenAI 兼容），不是 /api/coding（Anthropic 兼容）
ARK_API_KEY=${ARK_API_KEY}
ARK_BASE_URL=${ARK_BASE_URL}
ARK_LLM_MODEL=${ARK_LLM_MODEL}
ARK_EMBED_MODEL=${ARK_EMBED_MODEL}

# === Provider 切换 ===
LLM_PROVIDER=ark
EMBED_PROVIDER=ark

# Ollama 占位（不会被使用，但 config.py 仍会读，留着兼容）
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen:latest

# === Redis（本地）===
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL=21600

# === MySQL（本地）===
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=${MYSQL_APP_USER}
MYSQL_PASSWORD=${MYSQL_APP_PASSWORD}
MYSQL_DATABASE=${MYSQL_DATABASE}

# === ChromaDB ===
CHROMA_PATH=${APP_DIR}/chromadb_data

# === FastAPI ===
API_HOST=0.0.0.0
API_PORT=8000

# === Gradio 内部调 API ===
API_URL=http://127.0.0.1:8000

# === Gradio 访问鉴权（basic auth） ===
GRADIO_AUTH_USER=${GRADIO_AUTH_USER}
GRADIO_AUTH_PASSWORD=${GRADIO_AUTH_PASSWORD}

# === LLM 参数 ===
TEMPERATURE=0.4
TOP_K=3
MAX_TOKENS=500

# === 文档分块 ===
MAX_CHUNK_SIZE=1000
CHUNK_OVERLAP_RATIO=0.15

# === 会话 ===
MAX_HISTORY_ROUNDS=7
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 640 "$APP_DIR/.env"

echo "============================================================"
echo "  [4/5] 安装 systemd service"
echo "============================================================"

# ----- FastAPI -----
cat > /etc/systemd/system/my-rag-api.service <<EOF
[Unit]
Description=MY-RAG FastAPI backend
After=network.target redis-server.service mysql.service
Wants=redis-server.service mysql.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/scripts/start_api.py
Restart=always
RestartSec=5
# 1G 机器：限制内存，避免拖死系统
MemoryHigh=400M
MemoryMax=500M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ----- Gradio -----
cat > /etc/systemd/system/my-rag-gradio.service <<EOF
[Unit]
Description=MY-RAG Gradio frontend
After=network.target my-rag-api.service
Wants=my-rag-api.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/app/frontend/gradio_app.py
Restart=always
RestartSec=5
MemoryHigh=200M
MemoryMax=300M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable my-rag-api.service my-rag-gradio.service

echo "============================================================"
echo "  [5/5] 启动服务"
echo "============================================================"
systemctl restart my-rag-api.service
sleep 8
systemctl restart my-rag-gradio.service
sleep 5

systemctl --no-pager status my-rag-api.service     | head -15
echo
systemctl --no-pager status my-rag-gradio.service  | head -15

echo
echo "============================================================"
echo "  ✅ 部署完成"
echo "============================================================"
echo "  前端:  http://${PUBLIC_IP}:7860   (账号: ${GRADIO_AUTH_USER} / 密码: ${GRADIO_AUTH_PASSWORD})"
echo "  API :  http://${PUBLIC_IP}:8000"
echo "  LLM :  ${ARK_LLM_MODEL} (火山方舟)"
echo "  Embedding: ${ARK_EMBED_MODEL} (火山方舟)"
echo "  Rerank: BAAI/bge-reranker-v2-m3 (硅基流动)"
echo
echo "  常用命令:"
echo "    journalctl -u my-rag-api -f       # 看 API 日志"
echo "    journalctl -u my-rag-gradio -f    # 看前端日志"
echo "    systemctl restart my-rag-api      # 重启 API"
echo "    free -h && systemctl status my-rag-api  # 看内存占用"
echo "============================================================"
