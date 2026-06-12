#!/usr/bin/env bash
# =============================================================================
#  MY-RAG 服务器环境初始化脚本（Ubuntu 22.04 / 20.04）
#
#  ⚠️ 1G 内存版：不装 Ollama，LLM 走云端 API（硅基流动）
#                 自动配 2G swap，MySQL 用低内存配置
#
#  使用：
#      sudo bash server-setup.sh
# =============================================================================

set -e

# -------- 可调参数 --------
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-RagRoot@2026}"
MYSQL_APP_USER="${MYSQL_APP_USER:-rag}"
MYSQL_APP_PASSWORD="${MYSQL_APP_PASSWORD:-RagApp@2026}"
MYSQL_DATABASE="${MYSQL_DATABASE:-rag_db}"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-2048}"
# -------------------------

if [[ $EUID -ne 0 ]]; then
    echo "请用 root 或 sudo 运行: sudo bash $0"
    exit 1
fi

echo "============================================================"
echo "  [1/5] 配置 swap (${SWAP_SIZE_MB}MB) —— 1G 内存机器必备"
echo "============================================================"
if ! swapon --show | grep -q '^/swapfile'; then
    fallocate -l "${SWAP_SIZE_MB}M" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl vm.swappiness=10 || true
    echo "vm.swappiness=10" > /etc/sysctl.d/99-rag-swap.conf
    echo "  swap 已创建"
else
    echo "  swap 已存在，跳过"
fi
swapon --show
free -h

echo "============================================================"
echo "  [2/5] 系统更新 + Python 3.11 + 基础工具"
echo "============================================================"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
# Ubuntu 22.04 默认就是 Python 3.10/3.11，20.04 需要 deadsnakes
. /etc/os-release
if [[ "${VERSION_ID}" == "20.04" ]]; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
fi
apt-get install -y \
    curl wget git ufw \
    build-essential pkg-config \
    python3.11 python3.11-venv python3.11-dev python3-pip
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 || true

echo "============================================================"
echo "  [3/5] 安装 Redis（本地，仅 127.0.0.1）"
echo "============================================================"
apt-get install -y redis-server
sed -i 's/^# *bind .*/bind 127.0.0.1 ::1/' /etc/redis/redis.conf
sed -i 's/^bind .*/bind 127.0.0.1 ::1/'  /etc/redis/redis.conf
# 1G 机器：限制 Redis 最多用 64M
sed -i '/^maxmemory /d; /^maxmemory-policy /d' /etc/redis/redis.conf
echo "maxmemory 64mb" >> /etc/redis/redis.conf
echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
systemctl enable --now redis-server
systemctl restart redis-server
redis-cli ping

echo "============================================================"
echo "  [4/5] 安装 MySQL 8.0（本地，仅 127.0.0.1，低内存配置）"
echo "============================================================"
apt-get install -y mysql-server

# 低内存调优：把 InnoDB 缓冲池压到最小
mkdir -p /etc/mysql/mysql.conf.d
cat > /etc/mysql/mysql.conf.d/rag-low-mem.cnf <<EOF
[mysqld]
bind-address = 127.0.0.1
# 低内存调优（适合 1G 服务器）
innodb_buffer_pool_size = 64M
innodb_log_buffer_size = 8M
key_buffer_size = 8M
table_open_cache = 64
sort_buffer_size = 1M
read_buffer_size = 256K
read_rnd_buffer_size = 512K
net_buffer_length = 16K
thread_stack = 192K
performance_schema = OFF
EOF

systemctl enable --now mysql
systemctl restart mysql
sleep 5

# 设密码 + 建库 + 建用户
mysql --protocol=socket -uroot <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '${MYSQL_ROOT_PASSWORD}';
CREATE DATABASE IF NOT EXISTS \`${MYSQL_DATABASE}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${MYSQL_APP_USER}'@'localhost' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_APP_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "MySQL 已配置: root=${MYSQL_ROOT_PASSWORD}  app=${MYSQL_APP_USER}/${MYSQL_APP_PASSWORD}  db=${MYSQL_DATABASE}"

echo "============================================================"
echo "  [5/5] 配置防火墙（ufw）"
echo "============================================================"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     comment 'SSH'
ufw allow 8000/tcp   comment 'FastAPI'
ufw allow 7860/tcp   comment 'Gradio'
ufw --force enable
ufw status verbose

echo
echo "============================================================"
echo "  ✅ 服务器环境就绪（无 Ollama 版本）"
echo "============================================================"
echo "  Redis    : 127.0.0.1:6379  (限制 64M)"
echo "  MySQL    : 127.0.0.1:3306  user=${MYSQL_APP_USER} db=${MYSQL_DATABASE}"
echo "  LLM      : 走硅基流动云端 API（无本地模型）"
echo "  Swap     : ${SWAP_SIZE_MB}M"
echo "  防火墙   : 22 / 7860 / 8000"
echo
echo "  下一步：sudo -E bash $(dirname "$0")/install-app.sh"
echo "============================================================"
free -h
