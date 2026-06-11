# Gradio 应用 - 集成Hooks功能
import gradio as gr
import requests
import os
import sys

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
    """上传文件"""
    try:
        headers = {}
        if token:
            headers["token"] = token
        
        with open(file.name, 'rb') as f:
            response = requests.post(
                f"{API_URL}/upload",
                files={"file": ("uploaded_file", f, file.type)},
                headers=headers
            )
        response.raise_for_status()
        result = response.json()
        
        if result['code'] == 200:
            return f"✅ 上传成功！\n文件名: {result['data']['filename']}\n分块数量: {result['data']['chunks_count']}"
        else:
            return f"❌ 上传失败: {result['message']}"
    except Exception as e:
        return f"❌ 上传失败: {str(e)}"

def get_stats():
    """获取统计"""
    try:
        response = requests.get(f"{API_URL}/stats")
        response.raise_for_status()
        result = response.json()
        
        if result['code'] == 200:
            return f"知识库文档数量: {result['data']['document_count']}"
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
                
                refresh_btn.click(get_stats, outputs=stats_display)
                new_session_btn.click(
                    create_new_session,
                    inputs=[token_state],
                    outputs=[user_status, session_id]
                )
            
            with gr.Column(scale=3):
                gr.Markdown("### 📤 文档上传")
                file_upload = gr.File(label="上传PDF/TXT/Excel文件")
                upload_btn = gr.Button("上传到知识库")
                upload_result = gr.Textbox(label="上传结果", interactive=False)
                upload_btn.click(upload_file, inputs=[file_upload, token_state], outputs=upload_result)
        
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
        
        # 提交查询
        submit_btn.click(
            query_api,
            inputs=[query_input, session_id, token_state],
            outputs=[answer_output, context_output, session_display, timing_output, llm_output]
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
            query_api,
            inputs=[query_input, session_id, token_state],
            outputs=[answer_output, context_output, session_display, timing_output, llm_output]
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
    demo.launch(server_name="0.0.0.0", server_port=7860)