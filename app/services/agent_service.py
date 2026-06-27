# -*- coding: utf-8 -*-
"""多跳推理 Agent —— 把复杂问题拆成多步检索，逐跳累积信息，直到足够回答。

用法
====
    context = agent_service.multi_hop_search("A 产品定价？B 客户几折？", user_id)
    # 返回拼接后的文档文本，可直接喂给 before_model → wrap_model_call

不改变现有检索能力（hybrid_search / rerank / embedding），只在外面套编排层。
"""

import json
from app.services.retrieval_engine import retrieval_engine
from app.services.llm_service import llm_service
from app.utils.logger import logger
from app.utils.timer import time_block


# ── Prompt：把多跳问题拆成独立的子查询 ──
DECOMPOSE_PROMPT = """你是一个检索计划员。用户的问题可能包含多个子问题，需要分开检索。
请把问题拆成独立的子查询，每个子查询应该是一个可以直接检索的独立问题。
直接输出 JSON 数组，不要解释。

示例：
问题：A 产品最新定价策略是什么？B 客户能享受几折？
输出：["A 产品的定价策略", "B 客户的客户等级", "B 客户能享受的折扣规则"]

问题：{query}
输出："""

# ── Prompt：判断当前已检索到的信息是否足够 ──
SUFFICIENCY_PROMPT = """你是信息充分性判断员。

原始问题：{query}

已检索到的文档片段：
{context}

请判断：仅凭上述文档内容，能否完整回答原始问题中的所有子问题？
如果能 → 输出：{{"sufficient": true, "reason": "简短说明为什么够了"}}
如果不能 → 输出：{{"sufficient": false, "next_query": "还需要什么信息，用一句话表达"}}

直接输出 JSON，不要解释。"""


class AgentService:
    """多跳检索编排。

    接收原始用户 query → 拆子查询 → 逐跳检索 → 判断 → 直到信息足够。
    每跳复用 ``retrieval_engine.hybrid_search()``，不改变已有检索链路。
    """

    def __init__(self, max_hops: int = 5):
        self.max_hops = max_hops

    # ================================================================
    #  内部：调用 LLM 做元判断
    # ================================================================

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 做拆解 / 判断（失败时返回空字符串）。"""
        try:
            resp = llm_service.generate(prompt)
            if resp and "LLM调用失败" not in resp:
                return resp.strip()
        except Exception as e:
            logger.warning(f"Agent LLM 调用异常: {e}")
        return ""

    # ================================================================
    #  拆解：query → [子查询列表]
    # ================================================================

    def _decompose(self, query: str) -> list:
        """把原始问题拆成独立的子查询列表。

        拆失败时静默回退到 ``[query]``（退化到单次检索）。
        """
        prompt = DECOMPOSE_PROMPT.format(query=query)
        resp = self._call_llm(prompt)
        if not resp:
            return [query]

        try:
            start = resp.find("[")
            end = resp.rfind("]")
            if start >= 0 and end > start:
                queries = json.loads(resp[start : end + 1])
                if isinstance(queries, list) and queries:
                    return queries
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"拆解结果解析失败: {resp[:80]} → {e}")

        return [query]

    # ================================================================
    #  判断：当前 context 是否足够回答原始问题
    # ================================================================

    def _judge_sufficiency(self, query: str, context: str) -> dict:
        """判断已检索到的文档是否够回答原始问题。

        Returns:
            {"sufficient": True} 或
            {"sufficient": False, "next_query": "..."}
        """
        if not context.strip():
            return {"sufficient": False, "next_query": query}

        # context 太长时截断（避免 LLM 输入超限）
        max_context_chars = 3000
        truncated = context[:max_context_chars]
        if len(context) > max_context_chars:
            truncated += "\n\n...(省略)"

        prompt = SUFFICIENCY_PROMPT.format(query=query, context=truncated)
        resp = self._call_llm(prompt)
        if not resp:
            return {"sufficient": True}  # 保守地认为够用

        try:
            start = resp.find("{")
            end = resp.rfind("}")
            if start >= 0 and end > start:
                return json.loads(resp[start : end + 1])
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"充分性判断解析失败: {resp[:80]} → {e}")

        return {"sufficient": True}

    # ================================================================
    #  主入口：多跳检索
    # ================================================================

    def multi_hop_search(self, query: str, user_id: str = None) -> str:
        """多跳检索入口。

        1. 拆解原始问题为子查询列表
        2. 逐跳检索（每跳从待检索队列取一个子查询）
        3. 每跳后用 LLM 判断信息是否足够
        4. 不够 → 追加新查询 → 继续；足够 / 达最大跳数 → 结束

        Args:
            query: 用户原始问题
            user_id: 可选的用户 ID（按用户隔离检索）

        Returns:
            拼接后的文档文本（多条用 ``\\n\\n---\\n\\n`` 分隔）。
            未检索到任何内容时返回空字符串。
        """
        seen_docs: set = set()
        all_docs: list[str] = []

        # 1. 拆解
        with time_block("agent_decompose"):
            sub_queries = self._decompose(query)
        logger.info(f"[agent] 拆解: {query[:60]} → {sub_queries}")

        pending = list(sub_queries)  # 待处理的子查询队列

        for hop in range(self.max_hops):
            if not pending:
                logger.info(f"[agent] 第 {hop+1} 跳：队列空，结束")
                break

            sq = pending.pop(0)
            logger.info(f"[agent] 第 {hop+1}/{self.max_hops} 跳: '{sq[:60]}'")

            # 2. 检索（复用现有混合检索）
            with time_block(f"agent_hop_{hop+1}"):
                results = retrieval_engine.hybrid_search(sq, user_id)

            if not results:
                logger.info(f"[agent] 第 {hop+1} 跳: 无结果")
                continue

            # 3. 去重累积
            new_docs = []
            for r in results:
                doc = r.get("document", "")
                if doc and doc not in seen_docs:
                    seen_docs.add(doc)
                    all_docs.append(doc)
                    new_docs.append(doc)

            logger.info(
                f"[agent] 第 {hop+1} 跳: 检索 {len(results)} 条，"
                f"新增 {len(new_docs)} 条，累计 {len(all_docs)} 条"
            )

            # 4. 充分性判断
            with time_block(f"agent_judge_{hop+1}"):
                context_for_judge = "\n\n".join(all_docs[-10:])
                verdict = self._judge_sufficiency(query, context_for_judge)

            if verdict.get("sufficient"):
                logger.info(f"[agent] 第 {hop+1} 跳判断: ✅ 信息已足够")
                break

            # 5. 不够 → 追加查询
            next_q = verdict.get("next_query", "")
            if next_q and len(next_q) > 5 and next_q not in pending and next_q not in sub_queries:
                pending.append(next_q)
                logger.info(f"[agent] 追加查询: '{next_q[:60]}'")

            if hop == self.max_hops - 1:
                logger.warning(
                    f"[agent] 已达最大跳数 {self.max_hops}，"
                    f"返回已有 {len(all_docs)} 条文档"
                )

        return "\n\n---\n\n".join(all_docs) if all_docs else ""


agent_service = AgentService()
