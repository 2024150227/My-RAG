from fastapi import APIRouter, File, UploadFile, HTTPException, Header
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional, List
import asyncio
import time
from app.services.document_processor import document_processor
from app.services.embedding_service import embedding_service
from app.services.chroma_service import chroma_service
from app.services.retrieval_engine import retrieval_engine
from app.services.llm_service import llm_service
from app.services.memory_service import memory_service
from app.services.user_service import user_service
from app.services.hooks_manager import rag_hooks
from app.utils.logger import logger
import os

router = APIRouter()

# ==================== 用户认证接口 ====================

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    code: int
    message: str
    data: dict

@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """用户注册"""
    result = user_service.register(request.username, request.password)
    
    if result["success"]:
        return {
            'code': 200,
            'message': result["message"],
            'data': {'user_id': result["user_id"]}
        }
    else:
        return {
            'code': 400,
            'message': result["message"],
            'data': {}
        }

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """用户登录"""
    result = user_service.login(request.username, request.password)
    
    if result["success"]:
        return {
            'code': 200,
            'message': result["message"],
            'data': {
                'token': result["token"],
                'user_id': result["user_id"],
                'username': result["username"]
            }
        }
    else:
        return {
            'code': 401,
            'message': result["message"],
            'data': {}
        }

@router.post("/logout", response_model=AuthResponse)
async def logout(token: Optional[str] = Header(None)):
    """用户登出"""
    if not token:
        return {
            'code': 401,
            'message': '缺少认证令牌',
            'data': {}
        }
    
    result = user_service.logout(token)
    
    if result["success"]:
        return {
            'code': 200,
            'message': result["message"],
            'data': {}
        }
    else:
        return {
            'code': 500,
            'message': result["message"],
            'data': {}
        }

@router.get("/verify", response_model=AuthResponse)
async def verify_token(token: Optional[str] = Header(None)):
    """验证令牌"""
    if not token:
        return {
            'code': 401,
            'message': '缺少认证令牌',
            'data': {}
        }
    
    result = user_service.verify_token(token)
    
    if result["valid"]:
        return {
            'code': 200,
            'message': '令牌有效',
            'data': {
                'user_id': result["user_id"],
                'username': result["username"]
            }
        }
    else:
        return {
            'code': 401,
            'message': result["message"],
            'data': {}
        }

# ==================== 查询接口（集成Hooks） ====================

class QueryRequest(BaseModel):
    query: str
    session_id: str = None
    top_k: int = 3

class QueryResponse(BaseModel):
    code: int
    message: str
    data: dict
    request_id: str
    execution_time: float = None
    hooks_timing: dict = None
    llm_stats: dict = None

class BatchQueryRequest(BaseModel):
    queries: List[str]
    session_id: str = None
    top_k: int = 3

class BatchQueryResponse(BaseModel):
    code: int
    message: str
    data: List[dict]
    request_id: str
    total_execution_time: float = None
    batch_stats: dict = None

@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, token: Optional[str] = Header(None)):
    """
    查询接口（集成Hooks）
    流程：
    1. before-agent: 用户身份校验
    2. 检索相关文档
    3. before-model: Prompt预处理、敏感词过滤、上下文裁剪
    4. LLM生成
    5. after-model: 输出格式修正、二次敏感词过滤
    6. after-agent: 链路统计、数据持久化
    """
    request_id = str(uuid4())
    
    try:
        # ==================== before-agent 钩子 ====================
        if token:
            before_agent_result = rag_hooks.before_agent(token)
            
            if not before_agent_result["success"]:
                return {
                    'code': 401,
                    'message': before_agent_result["message"],
                    'data': {},
                    'request_id': request_id
                }
            
            session_id = before_agent_result["session_id"]
            user_id = before_agent_result["user_id"]
        else:
            # 无令牌时使用默认session
            session_id = request.session_id or str(uuid4())
            user_id = "anonymous"
        
        # ==================== 检索相关文档 ====================
        retrieved_docs = retrieval_engine.hybrid_search(request.query, user_id=user_id)
        retrieved_docs = [doc for doc in retrieved_docs if doc.get('document')]
        
        if not retrieved_docs:
            return {
                'code': 404,
                'message': '知识库内容未检索到相关信息',
                'data': {
                    'answer': '未找到相关信息',
                    'context': [],
                    'session_id': session_id
                },
                'request_id': request_id
            }
        
        context = "\n\n".join([doc['document'] for doc in retrieved_docs])
        
        # ==================== before-model 钩子 ====================
        before_model_result = rag_hooks.before_model(session_id, request.query, context)
        
        if before_model_result["is_blocked"]:
            return {
                'code': 403,
                'message': before_model_result["block_reason"],
                'data': {
                    'answer': '您的输入包含敏感内容，请重新提问。',
                    'context': [],
                    'session_id': session_id
                },
                'request_id': request_id
            }
        
        final_prompt = before_model_result["final_prompt"]
        
        # ==================== wrap_model_call 钩子（包裹LLM调用） ====================
        wrap_model_result = rag_hooks.wrap_model_call(session_id, request.query, final_prompt)
        
        if wrap_model_result["is_circuit_broken"]:
            return {
                'code': 503,
                'message': '服务暂时不可用，请稍后重试',
                'data': {
                    'answer': '抱歉，当前服务繁忙，请稍后重试。',
                    'context': retrieved_docs,
                    'session_id': session_id,
                    'user_id': user_id
                },
                'request_id': request_id,
                'execution_time': 0,
                'hooks_timing': {},
                'llm_stats': {
                    'token_count': 0,
                    'cache_hit': False,
                    'retry_count': wrap_model_result["retry_count"],
                    'is_circuit_broken': True
                }
            }
        
        answer = wrap_model_result["response"]
        llm_token_count = wrap_model_result["token_count"]
        
        # ==================== after-model 钩子 ====================
        after_model_result = rag_hooks.after_model(session_id, answer)
        
        if after_model_result["is_blocked"]:
            processed_answer = after_model_result["processed_output"]
        else:
            processed_answer = after_model_result["processed_output"]
        
        # ==================== after-agent 钩子 ====================
        after_agent_result = await rag_hooks.after_agent(
            session_id, 
            request.query, 
            processed_answer, 
            context
        )
        
        # 获取执行统计
        stats = rag_hooks.get_execution_stats(session_id)
        
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'answer': processed_answer,
                'context': retrieved_docs,
                'session_id': session_id,
                'user_id': user_id
            },
            'request_id': request_id,
            'execution_time': after_agent_result.get("total_time", 0),
            'hooks_timing': after_agent_result.get("hooks_timing", {}),
            'llm_stats': {
                'token_count': llm_token_count,
                'cache_hit': wrap_model_result.get("cache_hit", False),
                'retry_count': wrap_model_result.get("retry_count", 0),
                'is_circuit_broken': wrap_model_result.get("is_circuit_broken", False)
            }
        }
    
    except Exception as e:
        logger.error(f"查询失败: {str(e)}", extra={'request_id': request_id})
        return {
            'code': 500,
            'message': '服务内部异常',
            'data': {},
            'request_id': request_id
        }

# ==================== 文件上传接口 ====================

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), token: Optional[str] = Header(None)):
    request_id = str(uuid4())

    # ===== 鉴权：必须登录才能上传 =====
    if not token:
        return {
            'code': 401,
            'message': '请先登录后再上传文档',
            'data': {},
            'request_id': request_id
        }
    auth = user_service.verify_token(token)
    if not auth["valid"]:
        return {
            'code': 401,
            'message': auth["message"],
            'data': {},
            'request_id': request_id
        }
    user_id = auth["user_id"]

    try:
        # 文件存到 uploads/<user_id>/，多用户同名不会互相覆盖
        user_dir = f"uploads/{user_id}"
        os.makedirs(user_dir, exist_ok=True)
        file_path = f"{user_dir}/{file.filename}"

        with open(file_path, 'wb') as f:
            f.write(await file.read())

        content = document_processor.extract_text(file_path)

        if not content:
            return {
                'code': 5003,
                'message': '文档解析/切片失败',
                'data': {},
                'request_id': request_id
            }

        chunks = document_processor.semantic_chunking(content)

        if not chunks:
            return {
                'code': 5003,
                'message': '文档解析/切片失败',
                'data': {},
                'request_id': request_id
            }

        embeddings = embedding_service.get_batch_embeddings(chunks)

        valid_chunks = []
        valid_embeddings = []
        for chunk, embedding in zip(chunks, embeddings):
            if embedding:
                valid_chunks.append(chunk)
                valid_embeddings.append(embedding)

        if not valid_chunks:
            return {
                'code': 5001,
                'message': '向量模型API调用失败',
                'data': {},
                'request_id': request_id
            }

        ids = [f"doc_{user_id[:8]}_{uuid4().hex[:8]}_{i}" for i in range(len(valid_chunks))]
        # metadata 加 user_id，检索时按 user_id 过滤实现私有
        metadatas = [{
            'filename': file.filename,
            'chunk_index': i,
            'user_id': user_id,
        } for i in range(len(valid_chunks))]

        success = chroma_service.add_documents(valid_chunks, valid_embeddings, metadatas, ids)
        
        if success:
            return {
                'code': 200,
                'message': 'success',
                'data': {
                    'filename': file.filename,
                    'chunks_count': len(valid_chunks),
                    'embeddings_count': len(valid_embeddings)
                },
                'request_id': request_id
            }
        else:
            return {
                'code': 5002,
                'message': '数据库连接异常',
                'data': {},
                'request_id': request_id
            }
    
    except Exception as e:
        logger.error(f"上传失败: {str(e)}", extra={'request_id': request_id})
        return {
            'code': 500,
            'message': '服务内部异常',
            'data': {},
            'request_id': request_id
        }

# ==================== 批量查询接口（批处理优化） ====================

@router.post("/query/batch", response_model=BatchQueryResponse)
async def batch_query(request: BatchQueryRequest, token: Optional[str] = Header(None)):
    """
    批量查询接口（优化版）
    使用批处理和异步并发，大幅提升多问题查询性能
    """
    request_id = str(uuid4())
    start_time = time.time()
    
    try:
        # ==================== before-agent 钩子 ====================
        if token:
            before_agent_result = rag_hooks.before_agent(token)
            
            if not before_agent_result["success"]:
                return {
                    'code': 401,
                    'message': before_agent_result["message"],
                    'data': [],
                    'request_id': request_id,
                    'total_execution_time': 0,
                    'batch_stats': {}
                }
            
            session_id = before_agent_result["session_id"]
            user_id = before_agent_result["user_id"]
        else:
            session_id = request.session_id or str(uuid4())
            user_id = "anonymous"
        
        # ==================== 批量检索 ====================
        logger.info(f"开始批量查询，问题数: {len(request.queries)}")
        
        # 并发检索所有问题（使用线程池执行同步方法）
        import concurrent.futures
        
        def retrieve_sync(query):
            return retrieval_engine.hybrid_search(query, user_id=user_id)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            loop = asyncio.get_event_loop()
            retrieval_tasks = [
                loop.run_in_executor(executor, retrieve_sync, query)
                for query in request.queries
            ]
            all_retrieved_docs = await asyncio.gather(*retrieval_tasks, return_exceptions=True)
        
        # 处理检索结果
        results = []
        successful_queries = 0
        failed_queries = 0
        total_llm_tokens = 0
        cache_hits = 0
        
        for i, (query, retrieved_docs) in enumerate(zip(request.queries, all_retrieved_docs)):
            if isinstance(retrieved_docs, Exception):
                logger.error(f"查询 {i} 检索失败: {str(retrieved_docs)}")
                results.append({
                    'query': query,
                    'answer': '检索失败',
                    'context': [],
                    'success': False
                })
                failed_queries += 1
                continue
            
            retrieved_docs = [doc for doc in retrieved_docs if doc.get('document')]
            
            if not retrieved_docs:
                results.append({
                    'query': query,
                    'answer': '未找到相关信息',
                    'context': [],
                    'success': True
                })
                successful_queries += 1
                continue
            
            context = "\n\n".join([doc['document'] for doc in retrieved_docs])
            
            # ==================== before-model 钩子 ====================
            before_model_result = rag_hooks.before_model(session_id, query, context)
            
            if before_model_result["is_blocked"]:
                results.append({
                    'query': query,
                    'answer': '您的输入包含敏感内容，请重新提问。',
                    'context': [],
                    'success': True,
                    'blocked': True
                })
                successful_queries += 1
                continue
            
            final_prompt = before_model_result["final_prompt"]
            
            # ==================== wrap_model_call 钩子 ====================
            wrap_model_result = rag_hooks.wrap_model_call(session_id, query, final_prompt)
            
            if wrap_model_result["is_circuit_broken"]:
                results.append({
                    'query': query,
                    'answer': '抱歉，当前服务繁忙，请稍后重试。',
                    'context': retrieved_docs,
                    'success': False,
                    'circuit_broken': True
                })
                failed_queries += 1
                continue
            
            answer = wrap_model_result["response"]
            llm_token_count = wrap_model_result["token_count"]
            
            # ==================== after-model 钩子 ====================
            after_model_result = rag_hooks.after_model(session_id, answer)
            
            if after_model_result["is_blocked"]:
                processed_answer = after_model_result["processed_output"]
            else:
                processed_answer = after_model_result["processed_output"]
            
            # ==================== after-agent 钩子 ====================
            await rag_hooks.after_agent(session_id, query, processed_answer, context)
            
            # 统计信息
            total_llm_tokens += llm_token_count
            if wrap_model_result.get("cache_hit"):
                cache_hits += 1
            
            results.append({
                'query': query,
                'answer': processed_answer,
                'context': retrieved_docs,
                'success': True,
                'llm_stats': {
                    'token_count': llm_token_count,
                    'cache_hit': wrap_model_result.get("cache_hit", False),
                    'retry_count': wrap_model_result.get("retry_count", 0)
                }
            })
            successful_queries += 1
        
        total_time = time.time() - start_time
        
        logger.info(f"批量查询完成: 成功 {successful_queries}, 失败 {failed_queries}, 总耗时: {total_time:.3f}s")
        
        return {
            'code': 200,
            'message': 'success',
            'data': results,
            'request_id': request_id,
            'total_execution_time': total_time,
            'batch_stats': {
                'total_queries': len(request.queries),
                'successful_queries': successful_queries,
                'failed_queries': failed_queries,
                'total_llm_tokens': total_llm_tokens,
                'cache_hits': cache_hits,
                'cache_hit_rate': f"{(cache_hits / len(request.queries) * 100):.1f}%" if request.queries else "0%"
            }
        }
    
    except Exception as e:
        logger.error(f"批量查询失败: {str(e)}", extra={'request_id': request_id})
        return {
            'code': 500,
            'message': '服务内部异常',
            'data': [],
            'request_id': request_id,
            'total_execution_time': time.time() - start_time,
            'batch_stats': {}
        }

# ==================== 统计接口 ====================

@router.get("/stats")
async def get_stats(token: Optional[str] = Header(None)):
    try:
        # 登录用户：只统计自己的文档；未登录：返回 0（不暴露全局总数）
        user_id = None
        if token:
            auth = user_service.verify_token(token)
            if auth["valid"]:
                user_id = auth["user_id"]
        doc_count = chroma_service.count(user_id=user_id)
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'document_count': doc_count
            },
            'request_id': str(uuid4())
        }
    except Exception as e:
        logger.error(f"统计失败: {str(e)}")
        return {
            'code': 500,
            'message': '服务内部异常',
            'data': {},
            'request_id': str(uuid4())
        }

# ==================== 清空接口 ====================

@router.delete("/clear")
async def clear_database(token: Optional[str] = Header(None)):
    """清空当前登录用户的所有文档（仅自己的，不影响其他用户）"""
    request_id = str(uuid4())
    if not token:
        return {
            'code': 401,
            'message': '请先登录',
            'data': {},
            'request_id': request_id
        }
    auth = user_service.verify_token(token)
    if not auth["valid"]:
        return {
            'code': 401,
            'message': auth["message"],
            'data': {},
            'request_id': request_id
        }
    user_id = auth["user_id"]
    try:
        success = chroma_service.delete_by_user(user_id)
        if success:
            return {
                'code': 200,
                'message': 'success',
                'data': {},
                'request_id': request_id
            }
        else:
            return {
                'code': 5002,
                'message': '数据库连接异常',
                'data': {},
                'request_id': request_id
            }
    except Exception as e:
        logger.error(f"清空失败: {str(e)}")
        return {
            'code': 500,
            'message': '服务内部异常',
            'data': {},
            'request_id': request_id
        }

# ==================== 会话管理接口 ====================

@router.post("/session/new")
async def create_new_session(token: Optional[str] = Header(None)):
    """创建新会话"""
    if not token:
        return {
            'code': 401,
            'message': '缺少认证令牌',
            'data': {},
            'request_id': str(uuid4())
        }
    
    verify_result = user_service.verify_token(token)
    if not verify_result["valid"]:
        return {
            'code': 401,
            'message': verify_result["message"],
            'data': {},
            'request_id': str(uuid4())
        }
    
    session_id = user_service.create_new_session(verify_result["user_id"])
    
    return {
        'code': 200,
        'message': '新会话创建成功',
        'data': {'session_id': session_id},
        'request_id': str(uuid4())
    }

@router.get("/session/history/{session_id}")
async def get_session_history(session_id: str, token: Optional[str] = Header(None)):
    """获取会话历史记录"""
    try:
        # 获取短期记忆（Redis）
        short_history = memory_service.get_short_term_memory(session_id)
        
        # 获取长期记忆（MySQL）
        long_history = memory_service.get_long_term_memory(session_id)
        
        # 合并历史记录
        all_history = long_history + short_history
        
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'session_id': session_id,
                'history': all_history,
                'total_count': len(all_history)
            },
            'request_id': str(uuid4())
        }
    except Exception as e:
        logger.error(f"获取会话历史失败: {str(e)}")
        return {
            'code': 500,
            'message': '获取会话历史失败',
            'data': {
                'session_id': session_id,
                'history': [],
                'total_count': 0
            },
            'request_id': str(uuid4())
        }

@router.get("/execution-stats/{session_id}")
async def get_execution_stats(session_id: str):
    """获取执行统计"""
    stats = rag_hooks.get_execution_stats(session_id)
    
    return {
        'code': 200,
        'message': 'success',
        'data': stats,
        'request_id': str(uuid4())
    }