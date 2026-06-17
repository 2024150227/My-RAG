from fastapi import APIRouter, File, UploadFile, HTTPException, Header, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from uuid import uuid4
from typing import Optional, List
import asyncio
import json
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


# ==================== 图片相关辅助 ====================

# uploads 根目录（与 document_processor.UPLOAD_ROOT 保持一致）
_UPLOAD_ROOT = "uploads"


def _images_meta_to_urls(metadata: dict) -> list:
    """从单个 chunk 的 metadata 里把 images 字段拆成 URL 列表。

    metadata['images'] 是逗号分隔的相对路径（ChromaDB metadata 不支持 list）。
    URL 形如 ``/files/<相对路径>?token=xxx``，token 由前端拼。
    这里只返回相对路径，让前端拼绝对地址 + token。
    """
    if not metadata:
        return []
    raw = metadata.get('images') or ''
    if not raw:
        return []
    # 去重保序
    seen = set()
    paths = []
    for p in raw.split(','):
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


def _collect_image_urls(retrieved_docs: list) -> list:
    """把多个 chunk 的图片去重合并，返回相对路径列表。"""
    seen = set()
    urls = []
    for doc in retrieved_docs:
        meta = doc.get('metadata') or {}
        for p in _images_meta_to_urls(meta):
            if p not in seen:
                seen.add(p)
                urls.append(p)
    return urls


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

        # 检索文档涉及到的图片（去重后的相对路径列表）
        image_urls = _collect_image_urls(retrieved_docs)

        return {
            'code': 200,
            'message': 'success',
            'data': {
                'answer': processed_answer,
                'context': retrieved_docs,
                'images': image_urls,
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


# ==================== 流式查询接口（SSE） ====================

@router.post("/query/stream")
async def query_stream(request: QueryRequest, token: Optional[str] = Header(None)):
    """流式查询接口（Server-Sent Events）

    与 /query 共用前置检索、Hooks、敏感词过滤；仅 LLM 生成阶段改为流式输出，
    答案逐 token 推给前端。流结束后再调用 after-model / after-agent 钩子写历史。

    SSE 帧格式：
        data: {"type": "meta", "session_id": "...", "context": [...]}\\n\\n
        data: {"type": "token", "content": "你"}\\n\\n
        data: {"type": "token", "content": "好"}\\n\\n
        ...
        data: {"type": "done", "execution_time": 1.23, "hooks_timing": {...}}\\n\\n
    """
    request_id = str(uuid4())

    # ---------- 预处理：鉴权 + 检索 + before_model（同步部分） ----------
    try:
        if token:
            before_agent_result = rag_hooks.before_agent(token)
            if not before_agent_result["success"]:
                return _sse_error_response(401, before_agent_result["message"], request_id)
            session_id = before_agent_result["session_id"]
            user_id = before_agent_result["user_id"]
        else:
            session_id = request.session_id or str(uuid4())
            user_id = "anonymous"

        retrieved_docs = retrieval_engine.hybrid_search(request.query, user_id=user_id)
        retrieved_docs = [doc for doc in retrieved_docs if doc.get('document')]

        if not retrieved_docs:
            return _sse_error_response(404, '知识库内容未检索到相关信息', request_id, session_id=session_id)

        context = "\n\n".join([doc['document'] for doc in retrieved_docs])

        before_model_result = rag_hooks.before_model(session_id, request.query, context)
        if before_model_result["is_blocked"]:
            return _sse_error_response(403, before_model_result["block_reason"], request_id, session_id=session_id)

        final_prompt = before_model_result["final_prompt"]
    except Exception as e:
        logger.error(f"流式查询预处理失败: {str(e)}", extra={'request_id': request_id})
        return _sse_error_response(500, '服务内部异常', request_id)

    # ---------- 生成器：调 LLM 流 + 收尾钩子 ----------
    async def event_generator():
        start_time = time.time()
        try:
            # 1. 先发一个 meta 帧，告诉前端 session_id 和 context
            meta = {
                "type": "meta",
                "session_id": session_id,
                "user_id": user_id,
                "context": retrieved_docs,
                "images": _collect_image_urls(retrieved_docs),
                "request_id": request_id,
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

            # 2. 流式调 LLM，每个 token 发一帧
            answer_chunks = []
            for token_text in llm_service.generate_stream(request.query, final_prompt):
                answer_chunks.append(token_text)
                frame = {"type": "token", "content": token_text}
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
                # 让出事件循环，避免长时间占用
                await asyncio.sleep(0)

            answer = "".join(answer_chunks).strip()

            # 3. after-model 钩子（敏感词过滤、二次格式修正）
            after_model_result = rag_hooks.after_model(session_id, answer)
            processed_answer = after_model_result["processed_output"]

            # 4. 如果 after-model 修改了内容，发一帧"修正"通知前端
            if processed_answer != answer:
                fix_frame = {"type": "fixed", "content": processed_answer}
                yield f"data: {json.dumps(fix_frame, ensure_ascii=False)}\n\n"

            # 5. after-agent 钩子：历史落库、性能统计
            after_agent_result = await rag_hooks.after_agent(
                session_id, request.query, processed_answer, context
            )

            # 6. 收尾帧
            done_frame = {
                "type": "done",
                "execution_time": after_agent_result.get("total_time", time.time() - start_time),
                "hooks_timing": after_agent_result.get("hooks_timing", {}),
                "llm_stats": {
                    "token_count": len(answer_chunks),
                    "stream": True,
                },
            }
            yield f"data: {json.dumps(done_frame, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"流式生成异常: {str(e)}", extra={'request_id': request_id})
            err_frame = {"type": "error", "message": f"流式生成异常: {str(e)}"}
            yield f"data: {json.dumps(err_frame, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关 Nginx 缓冲，确保实时
        },
    )


def _sse_error_response(code: int, message: str, request_id: str, session_id: str = "") -> StreamingResponse:
    """流式接口的错误响应：仍以 SSE 帧返回，方便前端统一处理"""
    async def gen():
        frame = {
            "type": "error",
            "code": code,
            "message": message,
            "session_id": session_id,
            "request_id": request_id,
        }
        yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream; charset=utf-8")

# ==================== 文件上传接口 ====================

@router.get("/upload/check")
async def upload_check(filename: str, token: Optional[str] = Header(None)):
    """上传前检查同名文件是否已存在（按当前用户隔离）。

    前端建议在选中文件后先调一次本接口；若 exists=True，弹确认框
    询问用户是否覆盖；用户确认后再调 POST /upload?force=true。
    """
    request_id = str(uuid4())
    if not token:
        return {'code': 401, 'message': '请先登录', 'data': {}, 'request_id': request_id}
    auth = user_service.verify_token(token)
    if not auth["valid"]:
        return {'code': 401, 'message': auth["message"], 'data': {}, 'request_id': request_id}

    user_id = auth["user_id"]
    exists = chroma_service.exists_filename(user_id, filename)
    return {
        'code': 200,
        'message': 'success',
        'data': {'filename': filename, 'exists': exists},
        'request_id': request_id,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    force: bool = False,
    token: Optional[str] = Header(None),
):
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
        # 重名检测：默认拒绝；force=True 时先删旧再插新（覆盖语义）
        already_exists = chroma_service.exists_filename(user_id, file.filename)
        if already_exists and not force:
            return {
                'code': 4090,
                'message': f'文档 "{file.filename}" 已存在，请确认是否覆盖',
                'data': {'filename': file.filename, 'exists': True},
                'request_id': request_id,
            }
        if already_exists and force:
            removed = chroma_service.delete_by_filename(user_id, file.filename)
            logger.info(f"覆盖上传：已删除旧文件 {file.filename} 的 {removed} 个 chunk")

        # 文件存到 uploads/<user_id>/，多用户同名不会互相覆盖
        user_dir = f"uploads/{user_id}"
        os.makedirs(user_dir, exist_ok=True)
        file_path = f"{user_dir}/{file.filename}"

        with open(file_path, 'wb') as f:
            f.write(await file.read())

        # 同时抽文本和图（图抽不到不影响入库）
        result = document_processor.extract_text_and_images(file_path, user_id)
        content = result["text"]
        image_paths = result["images"]  # uploads/<user_id>/_images/<stem>/xxx.png

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
        # ChromaDB metadata 不支持 list，用逗号分隔字符串存图片相对路径。
        # 第一版：同一文档所有 chunk 共享该文档全部图（不做精细对齐）。
        images_csv = ','.join(image_paths)
        metadatas = [{
            'filename': file.filename,
            'chunk_index': i,
            'user_id': user_id,
            'images': images_csv,
        } for i in range(len(valid_chunks))]

        success = chroma_service.add_documents(valid_chunks, valid_embeddings, metadatas, ids)

        if success:
            return {
                'code': 200,
                'message': 'success',
                'data': {
                    'filename': file.filename,
                    'chunks_count': len(valid_chunks),
                    'embeddings_count': len(valid_embeddings),
                    'images_count': len(image_paths),
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

# ==================== 图片静态文件接口 ====================

@router.get("/files/{user_id}/{file_path:path}")
async def serve_user_file(
    user_id: str,
    file_path: str,
    token: Optional[str] = Query(None),
    token_header: Optional[str] = Header(None, alias="token"),
):
    """提供登录用户私有文件下载（主要用于检索结果中的图片）。

    URL 形如 ``/files/<user_id>/_images/<stem>/xxx.png?token=xxx``。
    因为 <img> 标签发不了自定义 header，token 默认走 query string；
    如果是程序化调用（带 header）也支持。

    安全性：
        1. token 必须有效
        2. token 对应的 user_id 必须与 URL 中 user_id 完全一致（防越权）
        3. 解析后的绝对路径必须在 uploads/<user_id>/ 内（防 ../ 穿越）
    """
    # 1. 鉴权：query 优先于 header（前端 <img> 用 query）
    auth_token = token or token_header
    if not auth_token:
        raise HTTPException(status_code=401, detail="缺少认证令牌")
    auth = user_service.verify_token(auth_token)
    if not auth.get("valid"):
        raise HTTPException(status_code=401, detail=auth.get("message") or "令牌无效")
    if auth["user_id"] != user_id:
        # 不能用别人的 token 看你的图，反之亦然
        raise HTTPException(status_code=403, detail="无权访问该文件")

    # 2. 路径合法性校验
    user_root = os.path.abspath(os.path.join(_UPLOAD_ROOT, user_id))
    target_abs = os.path.abspath(os.path.join(_UPLOAD_ROOT, user_id, file_path))
    if not target_abs.startswith(user_root + os.sep) and target_abs != user_root:
        raise HTTPException(status_code=403, detail="非法路径")
    if not os.path.isfile(target_abs):
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(target_abs)


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