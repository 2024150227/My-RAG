# MY-RAG 部署到云服务器（47.106.186.17）

> 目标：MySQL / Redis / Ollama / FastAPI / Gradio 全部以**本地原生服务**形式跑在 Ubuntu 上，不用任何容器。

## 📋 前置条件

- 一台 Ubuntu 22.04 / 20.04 服务器（你的：`47.106.186.17`）
- 至少 **8GB 内存**（跑 qwen3.5:latest 9.7B 的最低要求；4G 跑不动，建议 16G+）
- 至少 **30GB 磁盘**（系统 + Python 环境 + Ollama 模型 + ChromaDB）
- 云厂商**安全组放行端口**：`22 / 7860 / 8000`（脚本里也会配 ufw）
- 你的硅基流动 API Key

---

## 🚀 部署步骤

### 1. 把代码上传到服务器

在**本地** Windows 机器上：

```bash
# 在 Git Bash 或 PowerShell 里
ssh root@47.106.186.17 "mkdir -p /opt/my-rag"

# 把代码同步过去（排除大目录）
# Windows 没自带 rsync，用 scp 也行：
scp -r \
  app scripts deploy requirements.txt LICENSE README.md \
  root@47.106.186.17:/opt/my-rag/
```

或者直接 `git clone`（最干净）：

```bash
ssh root@47.106.186.17
cd /opt
git clone https://github.com/2024150227/My-RAG.git my-rag
```

### 2. 装环境（一次性）

```bash
ssh root@47.106.186.17
cd /opt/my-rag/deploy
chmod +x server-setup.sh install-app.sh
sudo bash server-setup.sh
```

这一步会：
- 装 Python 3.11、Redis、MySQL 8.0、Ollama
- 建好 MySQL 库 `rag_db` 和应用用户 `rag`
- 拉 `qwen3.5:latest`（约 6GB，看网速 5–20 分钟）
- 配防火墙

> 想改默认密码？在跑之前 `export MYSQL_APP_PASSWORD=xxx`，跟 install-app.sh 保持一致即可。

### 3. 部署应用

```bash
# 必须先把 API Key 传进环境变量
export SILICONFLOW_API_KEY=sk-bgqhrvgsciyceihcdellvcybcnpjrqriybfllervzrzzfzhq

sudo -E bash /opt/my-rag/deploy/install-app.sh
```

`-E` 是把当前环境变量传给 sudo，否则 `SILICONFLOW_API_KEY` 会丢。

这一步会：
- 建 `rag` 系统用户
- 创建 `/opt/my-rag/venv` 并装依赖
- 写 `.env`（指向本地 Redis/MySQL/Ollama）
- 安装并启动 systemd service：`my-rag-api`、`my-rag-gradio`

### 4. 验证

```bash
# 看服务状态
systemctl status my-rag-api my-rag-gradio

# 看日志
journalctl -u my-rag-api -f
journalctl -u my-rag-gradio -f

# 本机测一下
curl http://127.0.0.1:8000/
```

打开浏览器：
- **前端**：http://47.106.186.17:7860
- **API**：http://47.106.186.17:8000

---

## 🛠️ 日常运维

```bash
# 重启服务
systemctl restart my-rag-api
systemctl restart my-rag-gradio

# 看日志
journalctl -u my-rag-api -f --since "10 min ago"

# 改了 .env / 代码后
systemctl restart my-rag-api my-rag-gradio

# 看资源占用
systemctl status my-rag-api      # 内存、CPU
ollama ps                         # 看模型加载状态
redis-cli info memory
```

---

## 🐛 常见问题

### Q1：内存不够，Ollama OOM
症状：API 日志里 `LLM 调用失败: 500`，`ollama logs` 里有 `out of memory`。
解决：换更小的模型，比如 `qwen2.5:7b` 或 `qwen2.5:3b`。
```bash
ollama pull qwen2.5:7b
# 然后改 /opt/my-rag/.env 里的 OLLAMA_MODEL
sudo -u rag sed -i 's|^OLLAMA_MODEL=.*|OLLAMA_MODEL=qwen2.5:7b|' /opt/my-rag/.env
systemctl restart my-rag-api
```

### Q2：8000 / 7860 端口外网打不开
- 先 `curl http://127.0.0.1:8000/` 在服务器本机测；通了说明应用没问题
- 检查云厂商**安全组**（在网页控制台配的）放没放行
- 检查 `ufw status`：应该能看到 7860 / 8000 的 ALLOW

### Q3：MySQL 密码忘了
脚本里默认是 `RagRoot@2026 / RagApp@2026`。改密码：
```bash
sudo mysql -e "ALTER USER 'rag'@'localhost' IDENTIFIED BY '新密码';"
# 同步改 /opt/my-rag/.env 里的 MYSQL_PASSWORD
systemctl restart my-rag-api
```

### Q4：想停掉 / 卸载
```bash
systemctl stop my-rag-api my-rag-gradio
systemctl disable my-rag-api my-rag-gradio
rm /etc/systemd/system/my-rag-{api,gradio}.service
systemctl daemon-reload
# 数据
rm -rf /opt/my-rag
# Redis / MySQL / Ollama 如果不再用
apt-get remove --purge redis-server mysql-server
```

---

## 🔒 安全建议

1. **改密码**：脚本里默认密码先改了再用
2. **加访问限制**：Gradio 没自带账号，建议至少加：
   - 前置 Nginx + basic auth
   - 或 `demo.launch(auth=("user","pass"))`
3. **监控**：装 `prometheus-node-exporter`，至少要监控 CPU / 内存 / 磁盘
4. **HTTPS**：考虑用 Nginx + Let's Encrypt 证书加密
