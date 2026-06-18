# -*- coding: utf-8 -*-
"""链路节点耗时统计工具。

通过 contextvars 把 session_id 绑到当前请求/协程上下文，
让 services 层不用感知 "会话" 概念也能把耗时写到对应的统计池里。

用法：
    # 1. 入口处（before_agent / SSE 生成器入口）调一次
    set_session(session_id)

    # 2. 业务代码任意位置：
    with time_block("vector_search"):
        ...
    # 或装饰器
    @time_node("rerank")
    def rerank(...): ...

存储格式：rag_hooks.execution_stats[session_id]["node_timings"][name] = [秒, 秒, ...]
单位统一使用 **秒**（float），与 hooks_timing 保持一致。
"""

import time
import contextvars
from contextlib import contextmanager
from functools import wraps

# 当前请求的 session_id（async 友好，不同协程互不干扰）
_current_session: contextvars.ContextVar = contextvars.ContextVar(
    "rag_current_session", default=None
)


def set_session(session_id: str) -> None:
    """绑定当前上下文的 session_id。

    在 before_agent 钩子里调一次；SSE 流式接口的 event_generator
    入口也要再调一次（StreamingResponse 会切到新协程上下文）。
    """
    _current_session.set(session_id)


def get_session() -> str:
    """读取当前上下文绑定的 session_id（没有返回 None）。"""
    return _current_session.get()


def _record(name: str, duration_sec: float) -> None:
    """把节点耗时（秒）追加到 hooks 的统计池。

    懒导入 rag_hooks，避免 utils → services 循环引用。
    没有绑定 session_id 时静默丢弃，方便单元测试 / 脚本里直接 import。
    """
    sid = _current_session.get()
    if not sid:
        return

    from app.services.hooks_manager import rag_hooks
    stats = rag_hooks.execution_stats.setdefault(sid, {})
    timings = stats.setdefault("node_timings", {})
    # 保留 4 位小数，秒级精度足够
    timings.setdefault(name, []).append(round(duration_sec, 4))


@contextmanager
def time_block(name: str):
    """with 上下文管理器，统计代码块耗时（秒）。

    ::
        with time_block("vector_search"):
            results = chroma_service.query(...)
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(name, time.perf_counter() - t0)


def time_node(name: str):
    """装饰器版本，套到方法/函数上自动计时。

    ::
        @time_node("rerank")
        def rerank(self, query, docs):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with time_block(name):
                return func(*args, **kwargs)
        return wrapper
    return decorator
