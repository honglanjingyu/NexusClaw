# app/brain/intent_router.py
"""意图路由器 - 快速判断问题复杂度"""

import re
import time
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage

from .llm_client import get_llm_client
from .intent_types import IntentType, IntentResult
from .intent_rules import (
    FAST_RULES,
    SHORT_INPUT_MAX_LENGTH,
    SHORT_INPUT_CONFIDENCE,
    RULE_MATCH_CONFIDENCE,
    KNOWLEDGE_MAX_LENGTH_FOR_SIMPLE,
    REGEX_RULES,
    ENABLE_REGEX_MATCH,
    CACHE_SIZE,
    CACHE_TTL_SECONDS,
    LLM_FALLBACK_THRESHOLD,
    LLM_TIMEOUT_SECONDS,
)


class IntentCache:
    """简单的缓存管理器"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[IntentResult, float]] = {}  # key -> (result, timestamp)
        logger.info(f"IntentCache 初始化: max_size={max_size}, ttl={ttl_seconds}s")

    def _is_expired(self, timestamp: float) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return time.time() - timestamp > self.ttl_seconds

    def get(self, key: str) -> Optional[IntentResult]:
        if key in self._cache:
            result, timestamp = self._cache[key]
            if not self._is_expired(timestamp):
                return result
            else:
                del self._cache[key]
        return None

    def set(self, key: str, result: IntentResult):
        if self.max_size <= 0:
            return
        if len(self._cache) >= self.max_size:
            # 删除最旧的条目
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (result, time.time())

    def clear(self):
        self._cache.clear()


class IntentRouter:
    """
    意图路由器 - 快速区分简单/复杂问题

    策略：
    1. 先使用规则快速匹配（毫秒级）
    2. 不确定的情况才调用 LLM 判断（避免不必要的 LLM 调用）
    """

    def __init__(self, use_llm_for_uncertain: bool = True):
        self.llm = get_llm_client() if use_llm_for_uncertain else None
        self._cache = IntentCache(
            max_size=CACHE_SIZE if CACHE_SIZE > 0 else 100,
            ttl_seconds=CACHE_TTL_SECONDS
        )
        logger.info(f"IntentRouter 初始化完成: use_llm={use_llm_for_uncertain}")

    def _match_regex(self, user_input: str, patterns: List[str]) -> bool:
        """使用正则表达式匹配"""
        if not ENABLE_REGEX_MATCH or not patterns:
            return False
        try:
            for pattern in patterns:
                if re.search(pattern, user_input, re.IGNORECASE):
                    return True
        except Exception as e:
            logger.debug(f"正则匹配失败: {e}")
        return False

    def classify_by_rules(self, user_input: str) -> Optional[IntentResult]:
        """使用规则快速分类（不调用 LLM）"""
        user_input_lower = user_input.lower().strip()
        input_len = len(user_input)

        # 1. 超短输入 -> 简单意图
        if input_len <= SHORT_INPUT_MAX_LENGTH:
            return IntentResult(
                intent=IntentType.SIMPLE,
                confidence=SHORT_INPUT_CONFIDENCE,
                reason=f"超短输入（{input_len}字符）",
                needs_tools=False,
                needs_planning=False,
                estimated_complexity=1
            )

        # 2. 遍历规则匹配
        for intent_type, patterns in FAST_RULES.items():
            for pattern in patterns:
                if pattern in user_input_lower:
                    confidence = RULE_MATCH_CONFIDENCE.get(intent_type, 0.8)

                    # 知识检索额外判断：长输入可能需要复杂处理
                    if intent_type == IntentType.KNOWLEDGE and input_len > KNOWLEDGE_MAX_LENGTH_FOR_SIMPLE:
                        return IntentResult(
                            intent=IntentType.KNOWLEDGE,
                            confidence=0.6,
                            reason=f"匹配知识模式但输入较长({input_len}字符)",
                            needs_tools=True,
                            needs_planning=True,
                            estimated_complexity=2
                        )

                    return IntentResult(
                        intent=intent_type,
                        confidence=confidence,
                        reason=f"匹配关键词: {pattern}",
                        needs_tools=(intent_type == IntentType.KNOWLEDGE),
                        needs_planning=(intent_type == IntentType.COMPLEX),
                        estimated_complexity=1 if intent_type != IntentType.KNOWLEDGE else 2
                    )

        # 3. 正则表达式匹配（可选）
        if ENABLE_REGEX_MATCH:
            for intent_type, patterns in REGEX_RULES.items():
                if self._match_regex(user_input_lower, patterns):
                    confidence = 0.75
                    return IntentResult(
                        intent=intent_type,
                        confidence=confidence,
                        reason=f"正则匹配: {patterns[0] if patterns else 'unknown'}",
                        needs_tools=(intent_type == IntentType.KNOWLEDGE),
                        needs_planning=False,
                        estimated_complexity=1
                    )

        # 无法确定，返回 None 表示需要 LLM 判断
        return None

    async def classify_with_llm(self, user_input: str, session_id: str = "") -> IntentResult:
        """使用 LLM 分类（较慢，仅用于边界情况）"""
        if not self.llm:
            return IntentResult(
                intent=IntentType.COMPLEX,
                confidence=0.5,
                reason="LLM 不可用，默认复杂处理",
                needs_tools=True,
                needs_planning=True,
                estimated_complexity=3
            )

        prompt = f"""
请判断以下用户输入的问题类型：

用户输入: {user_input}

可选类型：
- simple: 简单问题（问候、闲聊、感谢、无需外部信息的普通问答）
- history: 历史查询（问我之前问过什么问题、查询对话历史）
- knowledge: 知识检索（需要查询知识库获取信息）
- complex: 复杂问题（需要多步分析、多个工具调用、复杂推理）

输出格式（JSON）：
{{
    "intent": "simple|history|knowledge|complex",
    "confidence": 0.0-1.0,
    "reason": "判断理由",
    "needs_tools": true/false,
    "needs_planning": true/false,
    "estimated_complexity": 1-5
}}

注意：
- 简单的你好、谢谢等 -> simple
- 问我问过什么、我之前问了什么 -> history  
- 需要查询知识库的 -> knowledge（needs_tools=true, needs_planning=false）
- 需要多步分析、复杂计算的 -> complex（needs_planning=true）
"""

        try:
            import asyncio
            messages = [
                SystemMessage(content="你是一个智能路由助手，快速判断问题类型。"),
                HumanMessage(content=prompt)
            ]

            result = await asyncio.wait_for(
                self.llm.invoke_structured(messages, IntentResult),
                timeout=LLM_TIMEOUT_SECONDS
            )
            logger.info(f"[会话 {session_id}] LLM 意图分类: {result.intent}, 置信度={result.confidence}")
            return result

        except asyncio.TimeoutError:
            logger.warning(f"[会话 {session_id}] LLM 意图分类超时")
            return IntentResult(
                intent=IntentType.COMPLEX,
                confidence=0.5,
                reason="LLM 调用超时",
                needs_tools=True,
                needs_planning=True,
                estimated_complexity=3
            )
        except Exception as e:
            logger.warning(f"[会话 {session_id}] LLM 意图分类失败: {e}")
            return IntentResult(
                intent=IntentType.COMPLEX,
                confidence=0.5,
                reason=f"分类失败: {str(e)}",
                needs_tools=True,
                needs_planning=True,
                estimated_complexity=3
            )

    async def route(
            self,
            user_input: str,
            session_id: str = "",
            use_cache: bool = True
    ) -> IntentResult:
        """
        路由主入口 - 先规则后 LLM

        Args:
            user_input: 用户输入
            session_id: 会话ID
            use_cache: 是否使用缓存

        Returns:
            IntentResult: 分类结果
        """
        # 缓存检查
        cache_key = f"{session_id}:{user_input[:50]}"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached:
                logger.debug(f"[会话 {session_id}] 使用缓存意图: {cached.intent}")
                return cached

        # 1. 规则快速匹配
        rule_result = self.classify_by_rules(user_input)

        # 高置信度规则匹配，直接使用
        if rule_result and rule_result.confidence >= LLM_FALLBACK_THRESHOLD:
            logger.info(f"[会话 {session_id}] 规则匹配: {rule_result.intent} (置信度={rule_result.confidence})")
            if use_cache:
                self._cache.set(cache_key, rule_result)
            return rule_result

        # 2. 低置信度或无匹配，使用 LLM 判断
        if rule_result:
            logger.debug(f"[会话 {session_id}] 规则匹配置信度较低({rule_result.confidence})，使用 LLM 确认")

        llm_result = await self.classify_with_llm(user_input, session_id)

        # 如果规则有结果，融合置信度
        if rule_result and llm_result.intent != rule_result.intent:
            logger.debug(f"[会话 {session_id}] 规则({rule_result.intent})与LLM({llm_result.intent})不一致，采用LLM结果")

        if use_cache:
            self._cache.set(cache_key, llm_result)

        return llm_result

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        logger.info("意图路由缓存已清空")


# 全局单例
_intent_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    """获取全局意图路由器"""
    global _intent_router
    if _intent_router is None:
        _intent_router = IntentRouter()
    return _intent_router