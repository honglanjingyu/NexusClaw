# app/agent/dream/vector_retriever.py
"""实体记忆向量检索模块 - 使用远程 Embedding API"""

import asyncio
import aiohttp
import numpy as np
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from loguru import logger
from functools import lru_cache


@dataclass
class VectorConfig:
    """向量检索配置"""
    # 远程 API 配置
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "text-embedding-v4"
    dimension: int = 1024

    # 检索配置
    min_similarity: float = 0.3
    batch_size: int = 10
    timeout: int = 30

    @classmethod
    def from_env(cls):
        """从 .env 文件加载配置"""
        import os
        from pathlib import Path
        from dotenv import load_dotenv

        # 加载环境变量
        env_paths = [
            Path.cwd() / ".env",
            Path(__file__).parent.parent.parent.parent / ".env",
            Path(__file__).parent.parent.parent / ".env",
        ]
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"加载配置: {env_path}")
                break

        return cls(
            api_key=os.getenv("LLM_API_KEY", "") or os.getenv("DASHSCOPE_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
            dimension=int(os.getenv("EMBEDDING_DIMENSIONS", "1024")),
            min_similarity=float(os.getenv("EMBEDDING_MIN_SIMILARITY", "0.3")),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "10")),
            timeout=int(os.getenv("EMBEDDING_TIMEOUT", "30"))
        )


class EmbeddingCache:
    """Embedding 缓存（避免重复调用 API）"""

    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, List[float]] = {}
        self._max_size = max_size

    def _get_key(self, text: str) -> str:
        """生成缓存键"""
        # 使用前200个字符作为键（避免太长）
        key_text = text[:200]
        return hashlib.md5(key_text.encode()).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        key = self._get_key(text)
        return self._cache.get(key)

    def set(self, text: str, embedding: List[float]):
        key = self._get_key(text)
        if len(self._cache) >= self._max_size:
            # 删除最早的条目
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = embedding

    def clear(self):
        self._cache.clear()


class RemoteEmbeddingClient:
    """远程 Embedding API 客户端"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.config = VectorConfig.from_env()
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache = EmbeddingCache()
        self._initialized = True

        logger.info(f"RemoteEmbeddingClient 初始化: model={self.config.model}, dimension={self.config.dimension}")

        if not self.config.api_key:
            logger.warning("⚠️ LLM_API_KEY 未配置，向量检索将不可用")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
        return self._session

    async def embed(self, text: str) -> Optional[List[float]]:
        """
        获取单个文本的向量

        Args:
            text: 输入文本

        Returns:
            向量列表，失败返回 None
        """
        if not self.config.api_key:
            return None

        # 检查缓存
        cached = self._cache.get(text)
        if cached:
            logger.debug(f"从缓存获取 embedding: {text[:50]}...")
            return cached

        # 调用 API
        embeddings = await self.embed_batch([text])
        if embeddings and len(embeddings) > 0:
            self._cache.set(text, embeddings[0])
            return embeddings[0]

        return None

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量获取文本向量

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        if not self.config.api_key:
            logger.warning("API Key 未配置")
            return []

        if not texts:
            return []

        # 过滤空文本
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return []

        # 检查缓存
        uncached_indices = []
        uncached_texts = []
        results = [None] * len(valid_texts)

        for i, text in enumerate(valid_texts):
            cached = self._cache.get(text)
            if cached:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # 批量调用 API
        if uncached_texts:
            api_results = await self._call_embedding_api(uncached_texts)

            # 更新结果和缓存
            for idx, (orig_idx, emb) in enumerate(zip(uncached_indices, api_results)):
                if emb:
                    results[orig_idx] = emb
                    self._cache.set(uncached_texts[idx], emb)

        # 过滤失败的
        return [r for r in results if r is not None]

    async def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """调用远程 Embedding API"""
        if not texts:
            return []

        url = f"{self.config.base_url.rstrip('/')}/embeddings"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        payload = {
            "model": self.config.model,
            "input": texts
        }

        try:
            session = await self._get_session()

            logger.debug(f"调用 Embedding API: {len(texts)} 条文本")

            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    # 解析结果
                    embeddings = [None] * len(texts)
                    for item in data.get("data", []):
                        index = item.get("index", 0)
                        embedding = item.get("embedding", [])
                        if index < len(embeddings):
                            embeddings[index] = embedding

                    success_count = len([e for e in embeddings if e])
                    logger.debug(f"Embedding API 成功: {success_count}/{len(texts)}")
                    return embeddings
                else:
                    error_text = await response.text()
                    logger.error(f"Embedding API 失败: {response.status} - {error_text}")
                    return []

        except asyncio.TimeoutError:
            logger.error("Embedding API 超时")
            return []
        except Exception as e:
            logger.error(f"Embedding API 异常: {e}")
            return []

    async def close(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if not a or not b:
            return 0.0

        a_arr = np.array(a)
        b_arr = np.array(b)

        # 归一化
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


# 全局单例
_embedding_client: Optional[RemoteEmbeddingClient] = None


def get_embedding_client() -> RemoteEmbeddingClient:
    """获取全局 Embedding 客户端"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = RemoteEmbeddingClient()
    return _embedding_client