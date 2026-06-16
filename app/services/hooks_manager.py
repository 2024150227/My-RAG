# Hooks管理器 - LangChain风格钩子实现
import time
import re
import hashlib
from datetime import datetime
from app.services.user_service import user_service
from app.services.memory_service import memory_service
from app.services.sensitive_filter import sensitive_filter
from app.services.llm_service import llm_service
from app.db.redis_client import redis_client
from app.utils.logger import logger

class RAGHooks:
    """RAG系统钩子管理器"""
    
    def __init__(self):
        self.execution_stats = {}
    
    # ==================== before-agent 钩子 ====================
    
    def before_agent(self, token: str) -> dict:
        """
        before-agent钩子：用户身份校验与会话初始化
        Args:
            token: 用户登录令牌
        Returns:
            {
                "success": bool,
                "message": str,
                "user_id": str,
                "session_id": str,
                "username": str
            }
        """
        start_time = time.time()
        
        try:
            # 1. 登录身份校验
            verify_result = user_service.verify_token(token)
            if not verify_result.get("valid"):
                logger.warning(f"[before-agent] 身份校验失败: {verify_result.get('message')}")
                return {
                    "success": False,
                    "message": verify_result.get("message", "身份校验失败"),
                    "user_id": None,
                    "session_id": None
                }
            
            user_id = verify_result["user_id"]
            username = verify_result["username"]
            
            # 2. 会话隔离加载
            session_id = user_service.get_user_session(user_id)
            
            # 记录执行统计
            self.execution_stats[session_id] = {
                "start_time": start_time,
                "user_id": user_id,
                "username": username,
                "hooks_timing": {}
            }
            
            hook_time = time.time() - start_time
            self.execution_stats[session_id]["hooks_timing"]["before_agent"] = hook_time
            
            logger.info(f"[before-agent] 用户 {username} 身份校验成功, session_id: {session_id}, 耗时: {hook_time:.3f}s")
            
            return {
                "success": True,
                "message": "身份校验成功",
                "user_id": user_id,
                "session_id": session_id,
                "username": username
            }
            
        except Exception as e:
            logger.error(f"[before-agent] 钩子执行失败: {str(e)}")
            return {
                "success": False,
                "message": f"钩子执行失败: {str(e)}",
                "user_id": None,
                "session_id": None
            }
    
    # ==================== before-model 钩子 ====================
    
    def before_model(self, session_id: str, user_query: str, retrieval_context: str) -> dict:
        """
        before-model钩子：请求预处理与上下文优化
        Args:
            session_id: 会话ID
            user_query: 用户查询
            retrieval_context: 检索召回结果
        Returns:
            {
                "success": bool,
                "message": str,
                "final_prompt": str,
                "is_blocked": bool,
                "block_reason": str
            }
        """
        start_time = time.time()

        try:
            # 1. 敏感词拦截过滤（仅检查用户原始 query，不查检索文档）
            #    避免知识库里包含 "病毒/攻击" 等正常术语时整条请求被误拦
            sensitive_result = sensitive_filter.filter_text(user_query)
            if sensitive_result["has_sensitive"]:
                logger.warning(f"[before-model] 用户输入命中敏感词: {sensitive_result['sensitive_words']}")
                return {
                    "success": False,
                    "message": "输入内容包含敏感词，已拦截",
                    "final_prompt": None,
                    "is_blocked": True,
                    "block_reason": f"检测到敏感词: {', '.join(sensitive_result['sensitive_words'])}"
                }

            # 2. 动态Prompt组装（在敏感词检查之后再拼接，节省一次正则扫描）
            history_str = memory_service.format_history_for_prompt(session_id)
            final_prompt = self._assemble_prompt(history_str, retrieval_context, user_query)

            # 3. 上下文裁剪控长
            final_prompt = self._trim_context(final_prompt)
            
            hook_time = time.time() - start_time
            if session_id in self.execution_stats:
                self.execution_stats[session_id]["hooks_timing"]["before_model"] = hook_time
            
            logger.info(f"[before-model] Prompt预处理完成, 长度: {len(final_prompt)}, 耗时: {hook_time:.3f}s")
            
            return {
                "success": True,
                "message": "Prompt预处理完成",
                "final_prompt": final_prompt,
                "is_blocked": False,
                "block_reason": None
            }
            
        except Exception as e:
            logger.error(f"[before-model] 钩子执行失败: {str(e)}")
            return {
                "success": False,
                "message": f"钩子执行失败: {str(e)}",
                "final_prompt": None,
                "is_blocked": True,
                "block_reason": str(e)
            }
    
    def _assemble_prompt(self, history: str, context: str, query: str) -> str:
        """动态组装Prompt"""
        prompt_parts = []
        
        if history:
            prompt_parts.append(history)
        
        if context:
            prompt_parts.append(f"\n检索到的相关内容：\n{context}\n")
        
        prompt_parts.append(f"\n用户问题：{query}")
        prompt_parts.append("\n请根据以上信息，给出准确、详细的回答。")
        
        return "\n".join(prompt_parts)
    
    def _trim_context(self, text: str) -> str:
        """上下文裁剪控长

        相比旧实现的改进：
        1. token 阈值提到 8192（旧值 4096 对 Qwen2.5 系列过于保守，模型本身支持 32K）
        2. 中文场景按 2 字符 ≈ 1 token 估算（旧值 4 偏宽松，可能导致实际 token 数超限）
        3. 优先按段落（``\\n\\n``）边界截断，避免砍在半句话/半个词中间
        """
        # 第一步：清洗文本
        text = self._clean_text(text)

        # 第二步：检查 token 数量
        max_tokens = 8192       # 模型上下文上限（保守留出系统提示与回复空间）
        char_per_token = 2      # 中文场景下更贴近真实的估算
        max_chars = max_tokens * char_per_token

        if len(text) <= max_chars:
            return text

        # 第三步：硬截断到 max_chars，再尝试退到最近的段落边界
        truncated = text[:max_chars]
        last_para = truncated.rfind("\n\n")
        # 段落边界不能离起点太近（否则丢的内容过多），至少保留 70%
        if last_para > max_chars * 0.7:
            truncated = truncated[:last_para]

        logger.warning(
            f"[before-model] 上下文超限（原 {len(text)} 字符），已截断至 {len(truncated)} 字符"
        )
        return truncated
    
    def _clean_text(self, text: str) -> str:
        """清洗文本"""
        # 剔除多余空格和换行
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # 剔除重复段落（简单实现）
        lines = text.split('\n')
        unique_lines = []
        for line in lines:
            if line.strip() and line not in unique_lines:
                unique_lines.append(line)
        
        return '\n'.join(unique_lines)
    
    # ==================== wrap_model_call 钩子 ====================
    
    def wrap_model_call(self, session_id: str, query: str, prompt: str) -> dict:
        """
        wrap_model_call钩子：包裹整个LLM调用，提供缓存、重试、熔断和Token统计
        Args:
            session_id: 会话ID
            query: 用户查询
            prompt: 完整的Prompt
        Returns:
            {
                "success": bool,
                "message": str,
                "response": str,
                "token_count": int,
                "cache_hit": bool,
                "retry_count": int,
                "is_circuit_broken": bool
            }
        """
        start_time = time.time()
        
        try:
            # 1. 检查缓存
            cache_key = self._generate_cache_key(query, prompt)
            cached_response = self._get_cached_response(cache_key)
            
            if cached_response:
                token_count = self._estimate_token_count(cached_response)
                hook_time = time.time() - start_time
                
                if session_id in self.execution_stats:
                    self.execution_stats[session_id]["hooks_timing"]["wrap_model_call"] = hook_time
                    self.execution_stats[session_id]["llm_token_count"] = token_count
                
                logger.info(f"[wrap_model_call] 缓存命中, query_hash: {cache_key[:8]}, token_count: {token_count}")
                
                return {
                    "success": True,
                    "message": "缓存命中",
                    "response": cached_response,
                    "token_count": token_count,
                    "cache_hit": True,
                    "retry_count": 0,
                    "is_circuit_broken": False
                }
            
            # 2. LLM调用（带重试和熔断）
            max_retries = 3
            retry_count = 0
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    response = llm_service.generate(query, prompt)
                    
                    if response and not response.startswith("LLM调用失败"):
                        # 成功，缓存结果
                        self._cache_response(cache_key, response)
                        
                        token_count = self._estimate_token_count(response)
                        hook_time = time.time() - start_time
                        
                        if session_id in self.execution_stats:
                            self.execution_stats[session_id]["hooks_timing"]["wrap_model_call"] = hook_time
                            self.execution_stats[session_id]["llm_token_count"] = token_count
                        
                        logger.info(f"[wrap_model_call] LLM调用成功, attempt: {attempt+1}, token_count: {token_count}")
                        
                        return {
                            "success": True,
                            "message": "LLM调用成功",
                            "response": response,
                            "token_count": token_count,
                            "cache_hit": False,
                            "retry_count": attempt,
                            "is_circuit_broken": False
                        }
                    
                    last_error = response or "LLM返回空或错误"
                    
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[wrap_model_call] LLM调用失败 attempt {attempt+1}: {last_error}")
                
                retry_count += 1
                
                # 指数退避等待
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1  # 1s, 2s, 4s
                    logger.info(f"[wrap_model_call] 等待 {wait_time}s 后重试...")
                    time.sleep(wait_time)
            
            # 3. 熔断：所有重试都失败
            logger.error(f"[wrap_model_call] 熔断触发: 重试 {max_retries} 次后仍失败")
            
            hook_time = time.time() - start_time
            if session_id in self.execution_stats:
                self.execution_stats[session_id]["hooks_timing"]["wrap_model_call"] = hook_time
            
            return {
                "success": False,
                "message": f"LLM调用失败，已熔断。最后错误: {last_error}",
                "response": None,
                "token_count": 0,
                "cache_hit": False,
                "retry_count": max_retries,
                "is_circuit_broken": True
            }
            
        except Exception as e:
            logger.error(f"[wrap_model_call] 钩子执行失败: {str(e)}")
            return {
                "success": False,
                "message": f"钩子执行失败: {str(e)}",
                "response": None,
                "token_count": 0,
                "cache_hit": False,
                "retry_count": 0,
                "is_circuit_broken": False
            }
    
    def _generate_cache_key(self, query: str, prompt: str) -> str:
        """生成缓存Key"""
        content = f"{query}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> str:
        """从Redis获取缓存"""
        try:
            cached = redis_client.get(f"llm_cache:{cache_key}")
            if cached:
                return cached.decode('utf-8') if isinstance(cached, bytes) else cached
            return None
        except Exception as e:
            logger.error(f"获取缓存失败: {str(e)}")
            return None
    
    def _cache_response(self, cache_key: str, response: str):
        """缓存响应到Redis（有效期5分钟）"""
        try:
            redis_client.setex(f"llm_cache:{cache_key}", 300, response)
        except Exception as e:
            logger.error(f"缓存响应失败: {str(e)}")
    
    def _estimate_token_count(self, text: str) -> int:
        """估算Token数量"""
        if not text:
            return 0
        # 中文约4字符=1token，英文约1字符=1token
        # 粗略估算：总字符数 / 2
        return len(text) // 2
    
    # ==================== after-model 钩子 ====================
    
    def after_model(self, session_id: str, model_output: str) -> dict:
        """
        after-model钩子：模型输出后置处理
        Args:
            session_id: 会话ID
            model_output: 模型输出内容
        Returns:
            {
                "success": bool,
                "message": str,
                "processed_output": str,
                "is_blocked": bool,
                "block_reason": str
            }
        """
        start_time = time.time()

        try:
            # 1. 输出格式修正
            processed_output = self._fix_output_format(model_output)

            # 注：不再对 LLM 输出做敏感词过滤——
            # 输入侧已经在 before_model 阶段对 user_query 拦截了恶意请求；
            # 输出侧再过滤会误伤包含技术术语（病毒/攻击/黑客等）的正常回答，
            # 且流式场景下逐 token 过滤实现复杂、用户体验差。

            hook_time = time.time() - start_time
            if session_id in self.execution_stats:
                self.execution_stats[session_id]["hooks_timing"]["after_model"] = hook_time

            logger.info(f"[after-model] 输出后处理完成, 耗时: {hook_time:.3f}s")
            
            return {
                "success": True,
                "message": "输出后处理完成",
                "processed_output": processed_output,
                "is_blocked": False,
                "block_reason": None
            }
            
        except Exception as e:
            logger.error(f"[after-model] 钩子执行失败: {str(e)}")
            return {
                "success": False,
                "message": f"钩子执行失败: {str(e)}",
                "processed_output": model_output,
                "is_blocked": False,
                "block_reason": None
            }
    
    def _fix_output_format(self, text: str) -> str:
        """修正输出格式"""
        # 剔除多余空格
        text = re.sub(r' +', ' ', text)
        
        # 统一换行符
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        
        # 剔除多余换行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    # ==================== after-agent 钩子 ====================
    
    async def after_agent(self, session_id: str, user_query: str, assistant_output: str, retrieval_context: str):
        """
        after-agent钩子：链路统计与数据持久化
        Args:
            session_id: 会话ID
            user_query: 用户查询
            assistant_output: 助手回答
            retrieval_context: 检索上下文
        Returns:
            {
                "success": bool,
                "message": str,
                "total_time": float,
                "hooks_timing": dict
            }
        """
        start_time = time.time()
        
        try:
            # 1. 全链路耗时统计
            if session_id in self.execution_stats:
                stats = self.execution_stats[session_id]
                total_time = time.time() - stats["start_time"]
                stats["total_time"] = total_time
                stats["hooks_timing"]["after_agent"] = time.time() - start_time
            else:
                total_time = 0
                stats = {"hooks_timing": {}}
            
            # 2. 会话数据落库（MySQL持久化）
            await memory_service.save_long_term_memory(
                session_id, 
                user_query, 
                assistant_output, 
                retrieval_context
            )
            
            # 3. 会话摘要缓存（Redis）
            memory_service.add_short_term_memory(session_id, user_query, assistant_output)
            
            # 生成会话摘要
            summary = self._generate_summary(user_query, assistant_output)
            self._cache_summary(session_id, summary)
            
            logger.info(f"[after-agent] 链路完成, 总耗时: {total_time:.3f}s")
            
            return {
                "success": True,
                "message": "链路统计与持久化完成",
                "total_time": total_time,
                "hooks_timing": stats.get("hooks_timing", {})
            }
            
        except Exception as e:
            logger.error(f"[after-agent] 钩子执行失败: {str(e)}")
            return {
                "success": False,
                "message": f"钩子执行失败: {str(e)}",
                "total_time": 0,
                "hooks_timing": {}
            }
    
    def _generate_summary(self, query: str, answer: str) -> str:
        """生成会话摘要"""
        # 简单摘要：截取问答关键内容
        query_summary = query[:50] if len(query) > 50 else query
        answer_summary = answer[:100] if len(answer) > 100 else answer
        return f"问: {query_summary} 答: {answer_summary}"
    
    def _cache_summary(self, session_id: str, summary: str):
        """缓存会话摘要到Redis"""
        from app.db.redis_client import redis_client
        try:
            redis_client.set(f"session:{session_id}:summary", summary)
        except Exception as e:
            logger.error(f"缓存摘要失败: {str(e)}")
    
    def get_execution_stats(self, session_id: str) -> dict:
        """获取执行统计"""
        return self.execution_stats.get(session_id, {})
    
    def clear_stats(self, session_id: str):
        """清除执行统计"""
        self.execution_stats.pop(session_id, None)

# 全局Hooks管理器
rag_hooks = RAGHooks()