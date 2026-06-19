# Gradio 应用 - 集成Hooks功能
import gradio as gr
import requests
import json
import os
import sys

# Gradio 启动时会用 httpx 访问 127.0.0.1 自检；如果系统设了 HTTP_PROXY/HTTPS_PROXY
# 又把本机也走代理，就会 [WinError 10061] 目标计算机积极拒绝。
# 这里把本机加进 NO_PROXY，确保启动自检与本地 API 调用都不走代理。
_no_proxy = os.environ.get("NO_PROXY", "")
for host in ("127.0.0.1", "localhost", "0.0.0.0"):
    if host not in _no_proxy:
        _no_proxy = (_no_proxy + "," + host).strip(",")
os.environ["NO_PROXY"] = _no_proxy
os.environ["no_proxy"] = _no_proxy

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from app.config import settings
    API_URL = os.getenv("API_URL", settings.API_URL)
except:
    API_URL = os.getenv("API_URL", "http://localhost:8000")

# ==================== 用户认证函数 ====================

def register_user(username, password):
    """用户注册"""
    try:
        response = requests.post(
            f"{API_URL}/register",
            json={"username": username, "password": password}
        )
        result = response.json()
        
        if result['code'] == 200:
            return f"✅ 注册成功！用户ID: {result['data']['user_id']}", "", ""
        else:
            return f"❌ 注册失败: {result['message']}", "", ""
    except Exception as e:
        return f"❌ 注册失败: {str(e)}", "", ""

def login_user(username, password):
    """用户登录"""
    try:
        response = requests.post(
            f"{API_URL}/login",
            json={"username": username, "password": password}
        )
        result = response.json()
        
        if result['code'] == 200:
            token = result['data']['token']
            user_id = result['data']['user_id']
            username = result['data']['username']
            return f"✅ 登录成功！欢迎 {username}", token, username
        else:
            return f"❌ 登录失败: {result['message']}", "", ""
    except Exception as e:
        return f"❌ 登录失败: {str(e)}", "", ""

def logout_user(token):
    """用户登出"""
    if not token:
        return "⚠️ 您尚未登录", "", ""
    
    try:
        response = requests.post(
            f"{API_URL}/logout",
            headers={"token": token}
        )
        result = response.json()
        
        if result['code'] == 200:
            return "✅ 登出成功", "", ""
        else:
            return f"❌ 登出失败: {result['message']}", "", ""
    except Exception as e:
        return f"❌ 登出失败: {str(e)}", "", ""

# ==================== 查询函数（集成Hooks） ====================

# 节点配色（按链路阶段分组）
#   蓝   = 检索类（embedding / vector / BM25）
#   绿   = 合并 / 后处理
#   黄   = 重排
#   灰   = 历史 / 缓存（轻量）
#   红   = LLM 推理（瓶颈强调色）
_NODE_PALETTE = [
    ("history_fetch",    "历史拉取",    "#9aa0a6"),
    ("query_embedding",  "问题向量化",  "#1a73e8"),
    ("vector_search",    "向量检索",    "#1a73e8"),
    ("bm25_search",      "BM25 检索",   "#34a853"),
    ("merge_dedup",      "合并去重",    "#34a853"),
    ("rerank",           "重排",        "#fbbc04"),
    ("llm_cache_lookup", "LLM 缓存",    "#9aa0a6"),
    ("llm_inference",    "LLM 推理",    "#ea4335"),
]


def render_waterfall(node_timings: dict, total_time: float) -> str:
    """节点耗时瀑布图（纯 HTML / CSS）。

    每行一个节点：左侧文字标签 + 右侧按耗时占比拉伸的彩色横条 +
    数值标注（秒 + 占比 %）。空数据返回提示文案。

    样式上用了独立的白底容器 + 深色文字，避免 Gradio 主题切到深色或灰底时
    文字颜色（#222 / #444）变得跟背景太接近导致看不清；条形上的数字也用
    带半透明白色描边，保证压在彩色条形上时仍清晰可读。
    """
    if not node_timings or total_time <= 0:
        return (
            "<div style='background:#ffffff;color:#1f1f1f;padding:12px;"
            "border:1px solid #e5e7eb;border-radius:6px;font-size:13px;'>"
            "暂无节点耗时数据，发起一次问答即可生成。</div>"
        )

    rows = []
    for key, label, color in _NODE_PALETTE:
        durations = node_timings.get(key) or []
        if not durations:
            continue
        dur = sum(durations)
        pct = (dur / total_time) * 100 if total_time > 0 else 0
        bar_w = max(pct, 0.4)  # 极短的节点至少给一点可见宽度

        rows.append(
            "<div style='display:flex;align-items:center;margin:6px 0;"
            "font-family:Consolas,Menlo,monospace;font-size:13px;'>"
            # 左侧标签：明确深色文字，避免主题切深色时不可见
            f"<div style='width:110px;flex-shrink:0;color:#1f1f1f;font-weight:600;'>{label}</div>"
            # 条形外框：浅灰底
            "<div style='flex:1;background:#e8eaed;height:24px;border-radius:3px;"
            "position:relative;overflow:hidden;'>"
            # 实际彩色条
            f"<div style='width:{bar_w:.2f}%;background:{color};height:100%;'></div>"
            # 数值标签：用 text-shadow 描边，保证在彩色条 / 浅灰底上都看得清
            "<span style='position:absolute;left:8px;top:0;line-height:24px;"
            "font-size:12px;color:#1f1f1f;font-weight:600;"
            "text-shadow:0 0 3px rgba(255,255,255,0.9),0 0 2px rgba(255,255,255,0.9);'>"
            f"{dur:.3f}s ({pct:.1f}%)</span>"
            "</div></div>"
        )

    if not rows:
        return (
            "<div style='background:#ffffff;color:#1f1f1f;padding:12px;"
            "border:1px solid #e5e7eb;border-radius:6px;font-size:13px;'>"
            "暂无节点耗时数据</div>"
        )

    header = (
        f"<div style='font-weight:700;margin-bottom:10px;color:#1f1f1f;"
        f"font-size:14px;'>总耗时 {total_time:.3f}s</div>"
    )
    # 整张图包一层白底卡片，主题切深色也能保证可读
    return (
        "<div style='background:#ffffff;color:#1f1f1f;padding:14px 16px;"
        "border:1px solid #e5e7eb;border-radius:6px;'>"
        + header + "".join(rows) +
        "</div>"
    )


def query_api(query, session_id, token):
    """查询API（带认证）"""
    try:
        headers = {}
        if token:
            headers["token"] = token

        response = requests.post(
            f"{API_URL}/query",
            json={
                "query": query,
                "session_id": session_id
            },
            headers=headers
        )
        response.raise_for_status()
        result = response.json()

        if result['code'] == 200:
            answer = result['data']['answer']
            context = result['data']['context']
            session_id = result['data']['session_id']
            execution_time = result.get('execution_time', 0)
            hooks_timing = result.get('hooks_timing', {})

            # 格式化上下文
            context_str = ""
            for i, ctx in enumerate(context, 1):
                context_str += f"**文档 {i}** (相关性: {ctx['relevance_score']:.4f})\n"
                context_str += ctx['document']
                context_str += "\n\n"

            # 格式化链路耗时
            timing_str = f"**总耗时**: {execution_time:.3f}秒\n\n"
            timing_str += "**各阶段耗时**:\n"
            for hook_name, hook_time in hooks_timing.items():
                timing_str += f"- {hook_name}: {hook_time:.3f}秒\n"

            # 格式化LLM统计信息
            llm_stats = result.get('llm_stats', {})
            llm_str = f"**输出Token数**: {llm_stats.get('token_count', 0)}\n"
            llm_str += f"**缓存命中**: {'✅ 是' if llm_stats.get('cache_hit') else '❌ 否'}\n"
            llm_str += f"**重试次数**: {llm_stats.get('retry_count', 0)}\n"
            llm_str += f"**熔断触发**: {'⚠️ 是' if llm_stats.get('is_circuit_broken') else '❌ 否'}\n"

            return answer, context_str, session_id, timing_str, llm_str, query
        elif result['code'] == 401:
            return "⚠️ 请先登录后再进行查询", "", session_id, "", "", ""
        elif result['code'] == 403:
            return f"⚠️ {result['message']}", "", session_id, "", "", ""
        else:
            return result['message'], "", session_id, "", "", ""
    except Exception as e:
        return f"❌ API调用失败: {str(e)}", "", session_id, "", "", ""


def query_api_stream(query, session_id, token):
    """流式查询 API：generator，逐 token yield 部分结果。

    每次 yield 7 元组（answer/context/session_id/timing/llm_str/image_urls/waterfall_html），
    让 Gradio 实时更新对应输出框。第一次 yield 给一个空答案表示"开始"，后续逐渐填充。
    """
    headers = {"Content-Type": "application/json"}
    if token:
        headers["token"] = token

    payload = {"query": query, "session_id": session_id}

    answer = ""
    context_str = ""
    timing_str = "⏳ 生成中..."
    llm_str = "⏳ 正在生成中... (流式输出已启用)"
    image_urls = []  # gr.Gallery 接受 url 列表
    waterfall_html = (
        "<div style='background:#ffffff;color:#1f1f1f;padding:12px;"
        "border:1px solid #e5e7eb;border-radius:6px;font-size:13px;'>"
        "⏳ 等待 LLM 输出完成...</div>"
    )

    # 先 yield 一次"开始"状态，让用户看到反馈
    yield answer, context_str, session_id, timing_str, llm_str, image_urls, waterfall_html

    try:
        with requests.post(
            f"{API_URL}/query/stream",
            json=payload,
            headers=headers,
            stream=True,
            timeout=300,
        ) as resp:
            if resp.status_code != 200:
                yield f"❌ HTTP {resp.status_code}", "", session_id, "", "", [], waterfall_html
                return

            # SSE 流是 UTF-8 字节流，但 requests.iter_lines(decode_unicode=True) 在
            # Windows 上有两个坑：
            #   1. SSE 响应头不带 charset → 回退到系统默认编码（cp936）解码
            #   2. 即使强制 resp.encoding='utf-8'，它也是按 chunk 边界单独解码，
            #      一个汉字 3 字节如果被切在两个 chunk 间就会出乱码方块
            # 解决：拿原始字节流，自己用增量 UTF-8 解码器（incremental codec）拼接，
            # 再按 \n 切行。这样无论字节怎么切都能正确还原中文。
            import codecs
            decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
            buffer = ''

            def _iter_sse_lines():
                nonlocal buffer
                for chunk in resp.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    buffer += decoder.decode(chunk)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        yield line.rstrip('\r')
                # 收尾 flush
                tail = decoder.decode(b'', final=True)
                if tail:
                    buffer += tail
                if buffer:
                    yield buffer.rstrip('\r')

            for raw in _iter_sse_lines():
                if not raw or not raw.startswith("data:"):
                    continue
                payload_str = raw[5:].strip()
                if not payload_str:
                    continue
                try:
                    frame = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue

                ftype = frame.get("type")

                if ftype == "meta":
                    # 上下文 + session_id 一次性渲染
                    session_id = frame.get("session_id", session_id)
                    context = frame.get("context", [])
                    context_str = ""
                    for i, ctx in enumerate(context, 1):
                        context_str += f"**文档 {i}** (相关性: {ctx.get('relevance_score', 0):.4f})\n"
                        context_str += ctx.get('document', '')
                        context_str += "\n\n"
                    # 图片：把后端返回的相对路径拼成带 token 的绝对 URL；
                    # 后端路径形如 uploads/<user_id>/_images/.../xxx.png，
                    # 静态路由是 /files/<user_id>/...，所以把 'uploads/' 前缀去掉
                    raw_imgs = frame.get("images", []) or []
                    image_urls = []
                    for p in raw_imgs:
                        rel = p[len("uploads/"):] if p.startswith("uploads/") else p
                        url = f"{API_URL}/files/{rel}"
                        if token:
                            url += f"?token={token}"
                        image_urls.append(url)
                    yield answer, context_str, session_id, timing_str, llm_str, image_urls, waterfall_html

                elif ftype == "token":
                    answer += frame.get("content", "")
                    yield answer, context_str, session_id, timing_str, llm_str, image_urls, waterfall_html

                elif ftype == "fixed":
                    # after-model 钩子修改了答案（例如敏感词过滤）
                    answer = frame.get("content", answer)
                    yield answer, context_str, session_id, timing_str, llm_str, image_urls, waterfall_html

                elif ftype == "done":
                    exec_t = frame.get("execution_time", 0)
                    hooks_timing = frame.get("hooks_timing", {})
                    node_timings = frame.get("node_timings", {})

                    timing_str = f"**总耗时**: {exec_t:.3f}秒\n\n**各阶段耗时**:\n"
                    for k, v in hooks_timing.items():
                        timing_str += f"- {k}: {v:.3f}秒\n"

                    stats = frame.get("llm_stats", {})
                    llm_str = (
                        f"**输出 token 数**: {stats.get('token_count', 0)}\n"
                        f"**流式输出**: ✅\n"
                    )

                    # 节点级瀑布图：基于后端返回的 node_timings 渲染
                    waterfall_html = render_waterfall(node_timings, exec_t)

                    yield answer, context_str, session_id, timing_str, llm_str, image_urls, waterfall_html

                elif ftype == "error":
                    msg = frame.get("message", "未知错误")
                    code = frame.get("code", 500)
                    if code == 401:
                        yield "⚠️ 请先登录后再进行查询", "", session_id, "", "", [], waterfall_html
                    elif code == 403:
                        yield f"⚠️ {msg}", "", session_id, "", "", [], waterfall_html
                    elif code == 404:
                        yield "未找到相关信息", "", session_id, "", "", [], waterfall_html
                    else:
                        yield f"❌ {msg}", "", session_id, "", "", [], waterfall_html
                    return

    except Exception as e:
        yield f"❌ API调用失败: {str(e)}", context_str, session_id, "", "", image_urls, waterfall_html

# ==================== 会话历史浏览函数 ====================

def load_session_history(session_id, token):
    """加载会话历史"""
    if not session_id:
        return [], 0
    
    try:
        headers = {}
        if token:
            headers["token"] = token
        
        response = requests.get(
            f"{API_URL}/session/history/{session_id}",
            headers=headers
        )
        response.raise_for_status()
        result = response.json()
        
        if result['code'] == 200:
            return result['data']['history'], result['data']['total_count']
        else:
            return [], 0
    except Exception as e:
        print(f"获取会话历史失败: {str(e)}")
        return [], 0

def show_prev_message(history, current_index):
    """显示上一条消息"""
    if not history or current_index <= 0:
        return "", "", "", "", "", -1, "⚠️ 无上一条聊天记录"
    
    new_index = current_index - 1
    item = history[new_index]
    
    # 格式化上下文
    context_str = ""
    if 'context' in item and item['context']:
        for i, ctx in enumerate(item['context'], 1):
            if isinstance(ctx, dict) and 'document' in ctx:
                relevance = ctx.get('relevance_score', 0)
                context_str += f"**文档 {i}** (相关性: {relevance:.4f})\n"
                context_str += ctx['document']
                context_str += "\n\n"
    
    return item.get('assistant_output', ""), context_str, "", "", "", new_index, f"消息 {new_index + 1}/{len(history)}"

def show_next_message(history, current_index):
    """显示下一条消息"""
    if not history or current_index >= len(history) - 1:
        return "", "", "", "", "", len(history), "⚠️ 无下一条聊天记录"
    
    new_index = current_index + 1
    item = history[new_index]
    
    # 格式化上下文
    context_str = ""
    if 'context' in item and item['context']:
        for i, ctx in enumerate(item['context'], 1):
            if isinstance(ctx, dict) and 'document' in ctx:
                relevance = ctx.get('relevance_score', 0)
                context_str += f"**文档 {i}** (相关性: {relevance:.4f})\n"
                context_str += ctx['document']
                context_str += "\n\n"
    
    return item.get('assistant_output', ""), context_str, "", "", "", new_index, f"消息 {new_index + 1}/{len(history)}"

# ==================== 其他函数 ====================

def upload_file(file, token):
    """上传文件（兼容老接口：直接上传，不做覆盖确认）"""
    return _do_upload(file, token, force=False)


def _do_upload(file, token, force=False):
    """实际执行上传的内部函数"""
    try:
        if file is None:
            return "⚠️ 请先选择要上传的文件"
        headers = {"token": token} if token else {}
        # Gradio 4.x 的 file 对象没有 .type 属性，所以这里不传 mime
        filename = os.path.basename(file.name)
        params = {"force": "true"} if force else None
        with open(file.name, 'rb') as f:
            response = requests.post(
                f"{API_URL}/upload",
                files={"file": (filename, f)},
                headers=headers,
                params=params,
            )
        response.raise_for_status()
        result = response.json()

        if result['code'] == 200:
            tag = "✅ 覆盖上传成功" if force else "✅ 上传成功"
            return f"{tag}！\n文件名: {result['data']['filename']}\n分块数量: {result['data']['chunks_count']}"
        else:
            return f"❌ 上传失败: {result['message']}"
    except Exception as e:
        return f"❌ 上传失败: {str(e)}"


def check_and_upload(file, token):
    """新版上传：先调 /upload/check 看是否同名，若已存在则提示用户确认覆盖。

    返回三个值，分别用于：
        - upload_result    : 上传结果文本
        - confirm_visible  : 覆盖确认按钮是否可见 (gr.update)
        - pending_filename : State，记录待覆盖的文件名（供"确认覆盖"按钮使用）
    """
    if file is None:
        return "⚠️ 请先选择要上传的文件", gr.update(visible=False), ""
    if not token:
        return "⚠️ 请先登录后再上传文档", gr.update(visible=False), ""

    filename = os.path.basename(file.name)

    try:
        check_resp = requests.get(
            f"{API_URL}/upload/check",
            params={"filename": filename},
            headers={"token": token},
            timeout=10,
        )
        check_resp.raise_for_status()
        check_result = check_resp.json()
    except Exception as e:
        return f"❌ 上传前检查失败: {str(e)}", gr.update(visible=False), ""

    if check_result.get("code") != 200:
        return f"❌ 检查失败: {check_result.get('message')}", gr.update(visible=False), ""

    exists = check_result.get("data", {}).get("exists", False)
    if exists:
        # 文件已存在，显示确认按钮，等用户决定
        msg = (
            f"⚠️ 文档 \"{filename}\" 已经上传过了，是否覆盖？\n\n"
            f"点击下方 \"✅ 确认覆盖\" 按钮继续，或取消后选择其他文件。"
        )
        return msg, gr.update(visible=True), filename

    # 不存在，直接上传
    return _do_upload(file, token, force=False), gr.update(visible=False), ""


def confirm_overwrite_upload(file, token, pending_filename):
    """用户点了"确认覆盖"按钮，强制以 force=true 重新上传。"""
    if not pending_filename:
        return "⚠️ 没有待覆盖的文件，请重新选择并点击上传", gr.update(visible=False), ""
    if file is None:
        return "⚠️ 文件已被清空，请重新选择", gr.update(visible=False), ""
    result_text = _do_upload(file, token, force=True)
    return result_text, gr.update(visible=False), ""

def get_stats(token=""):
    """获取当前用户的文档统计"""
    try:
        headers = {"token": token} if token else {}
        response = requests.get(f"{API_URL}/stats", headers=headers)
        response.raise_for_status()
        result = response.json()

        if result['code'] == 200:
            return f"我的知识库文档数量: {result['data']['document_count']}"
        else:
            return "获取统计失败"
    except Exception as e:
        return f"获取统计失败: {str(e)}"

def create_new_session(token):
    """创建新会话"""
    if not token:
        return "⚠️ 请先登录", ""
    
    try:
        response = requests.post(
            f"{API_URL}/session/new",
            headers={"token": token}
        )
        result = response.json()
        
        if result['code'] == 200:
            return f"✅ 新会话创建成功", result['data']['session_id']
        else:
            return f"❌ 创建失败: {result['message']}", ""
    except Exception as e:
        return f"❌ 创建失败: {str(e)}", ""

# ==================== Gradio界面 ====================

with gr.Blocks(title="企业级RAG知识库系统", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧠 企业级RAG知识库系统")
    gr.Markdown("基于LangChain Hooks机制，支持用户认证、敏感词过滤、链路统计等功能")
    
    # 状态变量
    token_state = gr.State("")
    session_id = gr.State("")
    chat_history = gr.State([])
    current_message_index = gr.State(-1)
    
    # ==================== 用户认证区域 ====================
    
    with gr.Tab("🔐 用户认证"):
        gr.Markdown("### 用户登录/注册")

        # 用一段 CSS 关闭浏览器的 autocomplete / autofill，
        # 避免 Chrome / Edge 把旧密码默认填进注册框。
        # 注：Gradio 没有暴露 autocomplete 属性，必须靠 JS 注入到 input。
        gr.HTML("""
        <script>
          // 进入页面后，把所有 type=password 的 input 关闭浏览器自动填充
          (function () {
            function disableAutofill() {
              document.querySelectorAll('input[type="password"]').forEach(function (el) {
                el.setAttribute('autocomplete', 'new-password');
                el.setAttribute('data-lpignore', 'true');     // LastPass
                el.setAttribute('data-1p-ignore', 'true');    // 1Password
                el.value = '';
              });
              document.querySelectorAll('input[type="text"]').forEach(function (el) {
                if (el.getAttribute('autocomplete') === null) {
                  el.setAttribute('autocomplete', 'off');
                }
              });
            }
            // 初次执行
            disableAutofill();
            // Gradio 是 SPA，组件可能延迟挂载，再多扫几遍
            setTimeout(disableAutofill, 500);
            setTimeout(disableAutofill, 2000);
          })();
        </script>
        """)

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("**注册新用户**")
                reg_username = gr.Textbox(label="用户名", placeholder="请输入用户名")
                reg_password = gr.Textbox(label="密码", placeholder="请输入密码", type="password")
                reg_btn = gr.Button("注册", variant="secondary")
                reg_result = gr.Textbox(label="注册结果", interactive=False)
                
                reg_btn.click(
                    register_user,
                    inputs=[reg_username, reg_password],
                    outputs=[reg_result, token_state, gr.State("")]
                )
            
            with gr.Column(scale=1):
                gr.Markdown("**用户登录**")
                login_username = gr.Textbox(label="用户名", placeholder="请输入用户名")
                login_password = gr.Textbox(label="密码", placeholder="请输入密码", type="password")
                login_btn = gr.Button("登录", variant="primary")
                login_result = gr.Textbox(label="登录结果", interactive=False)
                user_display = gr.Textbox(label="当前用户", interactive=False, visible=True)
                
                login_btn.click(
                    login_user,
                    inputs=[login_username, login_password],
                    outputs=[login_result, token_state, user_display]
                )
        
        gr.Markdown("---")
        logout_btn = gr.Button("登出", variant="stop")
        logout_result = gr.Textbox(label="登出结果", interactive=False)
        
        logout_btn.click(
            logout_user,
            inputs=[token_state],
            outputs=[logout_result, token_state, user_display]
        )
    
    # ==================== 智能问答区域 ====================
    
    with gr.Tab("💬 智能问答"):
        gr.Markdown("### 知识库问答")
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 会话管理")
                session_display = gr.Textbox(label="会话ID", interactive=False)
                user_status = gr.Textbox(label="用户状态", interactive=False)
                stats_display = gr.Textbox(label="知识库统计", interactive=False)
                
                with gr.Row():
                    refresh_btn = gr.Button("刷新统计", size="sm")
                    new_session_btn = gr.Button("新建会话", size="sm")
                
                refresh_btn.click(get_stats, inputs=[token_state], outputs=stats_display)
                new_session_btn.click(
                    create_new_session,
                    inputs=[token_state],
                    outputs=[user_status, session_id]
                )
            
            with gr.Column(scale=3):
                gr.Markdown("### 📤 文档上传")
                file_upload = gr.File(
                    label="上传文档（支持 PDF / Word(.docx) / Markdown / TXT / Excel）",
                    file_types=[".pdf", ".docx", ".md", ".txt", ".xlsx", ".xls"],
                )
                upload_btn = gr.Button("上传到知识库")
                upload_result = gr.Textbox(label="上传结果", interactive=False, lines=3)
                # 待覆盖文件名（隐藏 State）；命中重名后由 confirm_btn 复用
                pending_overwrite = gr.State("")
                # 确认覆盖按钮，默认隐藏；命中重名时由 check_and_upload 切到可见
                confirm_overwrite_btn = gr.Button(
                    "✅ 确认覆盖", variant="stop", visible=False
                )

                upload_btn.click(
                    check_and_upload,
                    inputs=[file_upload, token_state],
                    outputs=[upload_result, confirm_overwrite_btn, pending_overwrite],
                )
                confirm_overwrite_btn.click(
                    confirm_overwrite_upload,
                    inputs=[file_upload, token_state, pending_overwrite],
                    outputs=[upload_result, confirm_overwrite_btn, pending_overwrite],
                )
        
        gr.Markdown("---")
        
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### 💬 输入问题")
                query_input = gr.Textbox(label="输入您的问题", placeholder="例如：交互式建模（DSW）计费方式是什么？", lines=3)
                submit_btn = gr.Button("提交查询", variant="primary")
                
                with gr.Accordion("高级选项", open=False):
                    top_k = gr.Slider(minimum=1, maximum=10, value=3, step=1, label="返回文档数量")
            
            with gr.Column(scale=2):
                gr.Markdown("### 📝 LLM回答")
                answer_output = gr.Textbox(label="回答结果", lines=8, interactive=False)
                gr.Markdown("### 📷 相关图片")
                images_gallery = gr.Gallery(
                    label="文档内嵌图片",
                    columns=4,
                    height=220,
                    show_label=False,
                    preview=True,
                )
        
        gr.Markdown("---")
        
        # 会话历史浏览按钮
        with gr.Row():
            with gr.Column(scale=1):
                prev_btn = gr.Button("⬅️ 上一条对话", variant="secondary")
            with gr.Column(scale=1):
                history_status = gr.Textbox(label="历史状态", interactive=False, placeholder="历史记录导航")
            with gr.Column(scale=1):
                next_btn = gr.Button("下一条对话 ➡️", variant="secondary")
            with gr.Column(scale=1):
                refresh_history_btn = gr.Button("🔄 刷新历史", variant="secondary")
        
        gr.Markdown("---")
        
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### 📚 检索到的文档")
                context_output = gr.Textbox(label="上下文", lines=10, interactive=False)

            with gr.Column(scale=1):
                gr.Markdown("### ⏱️ 链路耗时统计")
                timing_output = gr.Textbox(label="执行耗时", lines=6, interactive=False)

            with gr.Column(scale=1):
                gr.Markdown("### 📊 LLM统计")
                llm_output = gr.Textbox(label="LLM信息", lines=6, interactive=False)

        # 节点级瀑布图：把链路黑盒拆开，一眼看出哪个节点最慢
        gr.Markdown("### 🔬 节点级耗时瀑布图")
        waterfall_output = gr.HTML(
            value=(
                "<div style='background:#ffffff;color:#1f1f1f;padding:12px;"
                "border:1px solid #e5e7eb;border-radius:6px;font-size:13px;'>"
                "暂无节点耗时数据，发起一次问答即可生成。</div>"
            ),
            label="节点耗时",
        )
        
        # 提交查询（流式）
        submit_btn.click(
            query_api_stream,
            inputs=[query_input, session_id, token_state],
            outputs=[answer_output, context_output, session_display, timing_output, llm_output, images_gallery, waterfall_output]
        ).then(
            # 查询完成后刷新历史
            load_session_history,
            inputs=[session_id, token_state],
            outputs=[chat_history, gr.State(0)]
        ).then(
            # 更新当前索引到最新消息
            lambda history: len(history) - 1 if history else -1,
            inputs=[chat_history],
            outputs=[current_message_index]
        )

        query_input.submit(
            query_api_stream,
            inputs=[query_input, session_id, token_state],
            outputs=[answer_output, context_output, session_display, timing_output, llm_output, images_gallery, waterfall_output]
        ).then(
            load_session_history,
            inputs=[session_id, token_state],
            outputs=[chat_history, gr.State(0)]
        ).then(
            lambda history: len(history) - 1 if history else -1,
            inputs=[chat_history],
            outputs=[current_message_index]
        )
        
        # 上一条对话
        prev_btn.click(
            show_prev_message,
            inputs=[chat_history, current_message_index],
            outputs=[answer_output, context_output, session_display, timing_output, llm_output, current_message_index, history_status]
        )
        
        # 下一条对话
        next_btn.click(
            show_next_message,
            inputs=[chat_history, current_message_index],
            outputs=[answer_output, context_output, session_display, timing_output, llm_output, current_message_index, history_status]
        )
        
        # 刷新历史
        refresh_history_btn.click(
            load_session_history,
            inputs=[session_id, token_state],
            outputs=[chat_history, gr.State(0)]
        ).then(
            lambda history: len(history) - 1 if history else -1,
            inputs=[chat_history],
            outputs=[current_message_index]
        ).then(
            lambda history: f"共 {len(history)} 条消息" if history else "暂无消息",
            inputs=[chat_history],
            outputs=[history_status]
        )
    
    # ==================== 系统说明 ====================
    
    with gr.Tab("📖 系统说明"):
        gr.Markdown("""
        ## 🧠 企业级RAG知识库系统
        
        ### 功能特性
        
        1. **用户认证系统**
           - 用户注册与登录
           - Token认证机制
           - 会话隔离
        
        2. **Hooks机制**
           - **before-agent**: 用户身份校验与会话初始化
           - **before-model**: Prompt预处理、敏感词过滤、上下文裁剪
           - **wrap_model_call**: 缓存、重试、熔断、Token统计
           - **after-model**: 输出格式修正、二次敏感词过滤
           - **after-agent**: 链路耗时统计、数据持久化
        
        3. **智能检索**
           - 混合检索（向量检索 + BM25关键字检索）
           - Rerank重排序
           - 语义分块
        
        4. **数据存储**
           - Redis: 短期会话记忆、用户信息缓存
           - MySQL: 聊天记录持久化
           - ChromaDB: 向量数据库
        
        ### 使用说明
        
        1. 在"用户认证"页面注册或登录
        2. 登录后切换到"智能问答"页面
        3. 输入问题进行查询
        4. 查看回答结果、检索文档和链路耗时统计
        
        ### API接口
        
        - `/register` - 用户注册
        - `/login` - 用户登录
        - `/logout` - 用户登出
        - `/query` - 查询接口
        - `/upload` - 文件上传
        - `/stats` - 统计信息
        - `/session/new` - 创建新会话
        - `/execution-stats/{session_id}` - 获取执行统计
        """)

if __name__ == "__main__":
    # 如果 .env 配置了 GRADIO_AUTH_USER/PASSWORD，则启用 basic auth
    auth = None
    try:
        if settings.GRADIO_AUTH_USER and settings.GRADIO_AUTH_PASSWORD:
            auth = (settings.GRADIO_AUTH_USER, settings.GRADIO_AUTH_PASSWORD)
            print(f"[Gradio] basic auth 已启用，用户: {settings.GRADIO_AUTH_USER}")
    except Exception:
        pass
    demo.launch(server_name="0.0.0.0", server_port=7860, auth=auth)