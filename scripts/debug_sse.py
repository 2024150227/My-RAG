# 直接打印 SSE 原始字节，定位乱码在前端还是后端
import requests
import sys

# 改成你测试时用的真实 token；没登录也能看到 401，那本身就够说明字节正常
TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
QUERY = sys.argv[2] if len(sys.argv) > 2 else "你好，介绍一下知识库"

resp = requests.post(
    "http://localhost:8000/query/stream",
    json={"query": QUERY, "session_id": ""},
    headers={"Content-Type": "application/json", "token": TOKEN},
    stream=True,
    timeout=120,
)

print(f"=== status: {resp.status_code} ===")
print(f"=== content-type: {resp.headers.get('content-type')} ===")
print(f"=== 前 500 字节（repr，看清是不是 UTF-8） ===")

count = 0
for chunk in resp.iter_content(chunk_size=128):
    if not chunk:
        continue
    print(repr(chunk))
    count += len(chunk)
    if count > 500:
        break

print(f"=== 总共看了 {count} 字节 ===")
