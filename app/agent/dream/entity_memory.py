# app/agent/dream/entity_memory.py
"""实体记忆存储 - 文件系统持久化（按类型和日期分层）"""

import json
import uuid
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from loguru import logger
import threading

from .models import EntityMemory, EntityType, MemoryQuery
from .config import dream_config


def sanitize_filename(text: str, max_len: int = 30) -> str:
    """清理文本，使其适合作为文件名"""
    # 移除或替换非法字符
    invalid_chars = r'[<>:"/\\|?*]'
    clean = re.sub(invalid_chars, '_', text)
    # 移除前后空格
    clean = clean.strip()
    # 截断长度
    if len(clean) > max_len:
        clean = clean[:max_len]
    # 如果为空，使用默认值
    if not clean:
        clean = "memory"
    return clean


def get_type_folder_name(entity_type: EntityType) -> str:
    """
    获取实体类型对应的文件夹名称

    映射关系:
    - USER_PREFERENCE -> pref
    - USER_FACT -> fact
    - KNOWLEDGE_INSIGHT -> insight
    - PATTERN -> pattern
    - CONTEXT -> context
    - CORRECTION -> correction
    """
    type_mapping = {
        EntityType.USER_PREFERENCE: "pref",
        EntityType.USER_FACT: "fact",
        EntityType.KNOWLEDGE_INSIGHT: "insight",
        EntityType.PATTERN: "pattern",
        EntityType.CONTEXT: "context",
        EntityType.CORRECTION: "correction",
    }
    return type_mapping.get(entity_type, entity_type.value[:8])


def parse_type_from_folder(folder_name: str) -> Optional[str]:
    """
    从文件夹名称解析实体类型
    """
    reverse_mapping = {
        "pref": "user_preference",
        "fact": "user_fact",
        "insight": "knowledge_insight",
        "pattern": "pattern",
        "context": "context",
        "correction": "correction",
    }
    return reverse_mapping.get(folder_name)


def generate_memory_filename(memory: EntityMemory) -> str:
    """
    生成有规律的文件名

    格式: YYYYMMDD_{entity_type_abbr}_{importance:03d}_{title_slug}_{uuid_short}.json

    示例: 20251215_pref_085_用户喜欢技术类内容_a1b2c3d4.json
    """
    date_str = memory.created_at.strftime("%Y%m%d")

    # 实体类型缩写
    type_abbr = {
        EntityType.USER_PREFERENCE: "pref",
        EntityType.USER_FACT: "fact",
        EntityType.KNOWLEDGE_INSIGHT: "insight",
        EntityType.PATTERN: "pattern",
        EntityType.CONTEXT: "context",
        EntityType.CORRECTION: "correction",
    }.get(memory.entity_type, memory.entity_type.value[:8])

    # 重要性转整数百分比（便于排序）
    importance_int = int(memory.importance_score * 100)

    # 标题清理
    title_slug = sanitize_filename(memory.title, max_len=40)

    # UUID 短码（前8位）
    uuid_short = memory.id[:8]

    # 组合文件名
    filename = f"{date_str}_{type_abbr}_{importance_int:03d}_{title_slug}_{uuid_short}.json"

    return filename


def parse_filename(filename: str) -> Optional[Dict[str, Any]]:
    """
    从文件名解析元数据

    解析结果包含: date, entity_type, importance, title_slug, uuid_short
    """
    # 移除 .json 后缀
    name = filename[:-5] if filename.endswith('.json') else filename

    parts = name.split('_', 4)  # 最多分5部分
    if len(parts) >= 4:
        return {
            "date": parts[0],
            "entity_type_abbr": parts[1],
            "importance": int(parts[2]) / 100,
            "title_slug": parts[3] if len(parts) > 3 else "",
            "uuid_short": parts[4] if len(parts) > 4 else "",
            "filename": filename
        }
    return None


class EntityMemoryStore:
    """
    实体记忆存储 - 基于文件系统（按类型和日期分层）

    目录结构:
    entity_memory/
    ├── memory_index.json
    ├── pref/
    │   ├── 20251215/
    │   │   └── 20251215_pref_085_xxx.json
    │   └── 20251216/
    │       └── 20251216_pref_090_yyy.json
    ├── fact/
    │   └── 20251215/
    │       └── 20251215_fact_080_zzz.json
    ├── insight/
    ├── pattern/
    └── correction/
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.base_dir = Path.cwd() / dream_config.ENTITY_MEMORY_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self._cache: Dict[str, EntityMemory] = {}
        self._index_file = self.base_dir / "memory_index.json"
        self._cache_loaded = False
        self._cache_lock = threading.Lock()
        self._index: Dict[str, Dict[str, Any]] = {}  # memory_id -> metadata

        self._load_all()
        self._initialized = True

        logger.info(f"EntityMemoryStore 初始化: {self.base_dir}, 已加载 {len(self._cache)} 条记忆")

    def _get_type_dir(self, entity_type: EntityType) -> Path:
        """获取类型文件夹路径"""
        folder_name = get_type_folder_name(entity_type)
        type_dir = self.base_dir / folder_name
        type_dir.mkdir(parents=True, exist_ok=True)
        return type_dir

    def _get_date_dir(self, entity_type: EntityType, date_str: str) -> Path:
        """获取日期文件夹路径"""
        type_dir = self._get_type_dir(entity_type)
        date_dir = type_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir

    def _get_file_path(self, memory: EntityMemory) -> Path:
        """获取记忆文件路径（基于类型和日期分层）"""
        date_str = memory.created_at.strftime("%Y%m%d")
        date_dir = self._get_date_dir(memory.entity_type, date_str)
        filename = generate_memory_filename(memory)
        return date_dir / filename

    def _get_file_path_by_id(self, memory_id: str) -> Optional[Path]:
        """根据记忆ID查找文件路径"""
        # 先从索引中查找
        if memory_id in self._index:
            index_entry = self._index[memory_id]
            type_folder = index_entry.get("type_folder")
            date_folder = index_entry.get("date_folder")
            filename = index_entry.get("filename")

            if type_folder and date_folder and filename:
                file_path = self.base_dir / type_folder / date_folder / filename
                if file_path.exists():
                    return file_path

        # 回退：扫描目录查找
        for type_dir in self.base_dir.iterdir():
            if not type_dir.is_dir() or type_dir.name == "memory_index.json":
                continue
            for date_dir in type_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                for file_path in date_dir.glob("*.json"):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if data.get("id") == memory_id:
                                return file_path
                    except Exception:
                        continue
        return None

    def _update_index(self, memory: EntityMemory, file_path: Path):
        """更新索引文件"""
        date_str = memory.created_at.strftime("%Y%m%d")
        type_folder = get_type_folder_name(memory.entity_type)

        self._index[memory.id] = {
            "id": memory.id,
            "type_folder": type_folder,
            "date_folder": date_str,
            "filename": file_path.name,
            "full_path": str(file_path.relative_to(self.base_dir)),
            "entity_type": memory.entity_type.value,
            "title": memory.title,
            "importance_score": memory.importance_score,
            "created_at": memory.created_at.isoformat(),
            "tags": memory.tags
        }
        self._save_index()

    def _remove_from_index(self, memory_id: str):
        """从索引中移除"""
        if memory_id in self._index:
            del self._index[memory_id]
            self._save_index()

    def _save_index(self):
        """保存索引文件"""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
            logger.debug(f"索引已保存，共 {len(self._index)} 条记录")
        except Exception as e:
            logger.error(f"保存索引失败: {e}")

    def _load_index(self):
        """加载索引文件"""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                logger.debug(f"索引已加载，共 {len(self._index)} 条记录")
            except Exception as e:
                logger.error(f"加载索引失败: {e}")
                self._index = {}

    def _save_memory(self, memory: EntityMemory):
        """保存单条记忆（使用分层目录）"""
        file_path = self._get_file_path(memory)

        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(memory.to_dict(), f, ensure_ascii=False, indent=2)

            # 更新索引
            self._update_index(memory, file_path)

            logger.debug(f"保存记忆: {file_path}")
        except Exception as e:
            logger.error(f"保存记忆失败 {memory.id}: {e}")

    def _load_memory_from_path(self, file_path: Path) -> Optional[EntityMemory]:
        """从文件路径加载记忆"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return EntityMemory.from_dict(data)
        except Exception as e:
            logger.error(f"加载记忆失败 {file_path}: {e}")
            return None

    def _load_all(self):
        """加载所有记忆到缓存（递归扫描所有子目录）"""
        # 先加载索引
        self._load_index()

        with self._cache_lock:
            self._cache.clear()

            if not self.base_dir.exists():
                return

            # 递归扫描所有 json 文件
            for file_path in self.base_dir.rglob("*.json"):
                if file_path.name == "memory_index.json":
                    continue

                memory = self._load_memory_from_path(file_path)
                if memory:
                    self._cache[memory.id] = memory

            self._cache_loaded = True
            logger.info(f"加载了 {len(self._cache)} 条实体记忆")

    def save(self, memory: EntityMemory) -> str:
        """保存记忆"""
        with self._cache_lock:
            self._cache[memory.id] = memory
        self._save_memory(memory)
        logger.info(f"记忆已保存: {memory.entity_type.value} - {memory.title[:50]}")
        return memory.id

    def save_multi(self, memories: List[EntityMemory]) -> List[str]:
        """批量保存记忆"""
        ids = []
        for memory in memories:
            ids.append(self.save(memory))
        return ids

    def get(self, memory_id: str) -> Optional[EntityMemory]:
        """获取记忆"""
        with self._cache_lock:
            memory = self._cache.get(memory_id)

        if memory:
            # 更新访问统计
            memory.access_count += 1
            memory.last_accessed = datetime.now()
            self._save_memory(memory)

        return memory

    def get_all(self) -> List[EntityMemory]:
        """获取所有记忆"""
        with self._cache_lock:
            return list(self._cache.values())

    def get_by_type(self, entity_type: EntityType) -> List[EntityMemory]:
        """按类型获取记忆"""
        with self._cache_lock:
            return [m for m in self._cache.values() if m.entity_type == entity_type]

    def get_by_date(self, date_str: str) -> List[EntityMemory]:
        """按日期获取记忆（日期格式: YYYYMMDD）"""
        results = []
        with self._cache_lock:
            for memory in self._cache.values():
                if memory.created_at.strftime("%Y%m%d") == date_str:
                    results.append(memory)
        return results

    def get_by_type_and_date(self, entity_type: EntityType, date_str: str) -> List[EntityMemory]:
        """按类型和日期获取记忆"""
        results = []
        with self._cache_lock:
            for memory in self._cache.values():
                if memory.entity_type == entity_type and memory.created_at.strftime("%Y%m%d") == date_str:
                    results.append(memory)
        return results

    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        file_path = self._get_file_path_by_id(memory_id)

        with self._cache_lock:
            if memory_id in self._cache:
                del self._cache[memory_id]

        self._remove_from_index(memory_id)

        if file_path and file_path.exists():
            file_path.unlink()
            # 尝试删除空的日期文件夹
            try:
                if file_path.parent.exists() and not any(file_path.parent.iterdir()):
                    file_path.parent.rmdir()
            except Exception:
                pass
            logger.info(f"删除记忆: {memory_id} -> {file_path}")
            return True

        logger.warning(f"记忆文件不存在: {memory_id}")
        return False

    def delete_by_type(self, entity_type: str) -> int:
        """按实体类型删除所有记忆"""
        count = 0
        type_folder = get_type_folder_name(EntityType(entity_type) if isinstance(entity_type, str) else entity_type)
        type_dir = self.base_dir / type_folder

        if type_dir.exists():
            # 收集要删除的记忆ID
            ids_to_delete = []
            for date_dir in type_dir.iterdir():
                if date_dir.is_dir():
                    for file_path in date_dir.glob("*.json"):
                        memory = self._load_memory_from_path(file_path)
                        if memory:
                            ids_to_delete.append(memory.id)
                            count += 1
                        file_path.unlink()

            # 从缓存和索引中删除
            with self._cache_lock:
                for mid in ids_to_delete:
                    if mid in self._cache:
                        del self._cache[mid]
                    if mid in self._index:
                        del self._index[mid]

            # 删除目录
            import shutil
            shutil.rmtree(type_dir)
            self._save_index()

            logger.info(f"按类型删除: {type_folder}, 共 {count} 条记忆")

        return count

    def delete_by_date_range(self, start_date: str, end_date: str) -> int:
        """按日期范围删除记忆"""
        count = 0

        # 扫描所有类型目录
        for type_dir in self.base_dir.iterdir():
            if not type_dir.is_dir() or type_dir.name == "memory_index.json":
                continue

            for date_dir in type_dir.iterdir():
                if not date_dir.is_dir():
                    continue

                date_str = date_dir.name
                if start_date <= date_str <= end_date:
                    # 收集该日期目录下的记忆ID
                    ids_to_delete = []
                    for file_path in date_dir.glob("*.json"):
                        memory = self._load_memory_from_path(file_path)
                        if memory:
                            ids_to_delete.append(memory.id)
                            count += 1
                        file_path.unlink()

                    # 从缓存和索引中删除
                    with self._cache_lock:
                        for mid in ids_to_delete:
                            if mid in self._cache:
                                del self._cache[mid]
                            if mid in self._index:
                                del self._index[mid]

                    # 删除空目录
                    try:
                        date_dir.rmdir()
                    except Exception:
                        pass

        self._save_index()
        logger.info(f"按日期范围删除: {start_date}~{end_date}, 共 {count} 条记忆")
        return count

    def delete_by_importance_below(self, min_importance: float) -> int:
        """删除重要性低于阈值的记忆"""
        count = 0
        ids_to_delete = []

        with self._cache_lock:
            for memory_id, memory in self._cache.items():
                if memory.importance_score < min_importance:
                    ids_to_delete.append(memory_id)

        for memory_id in ids_to_delete:
            if self.delete(memory_id):
                count += 1

        logger.info(f"按重要性删除: threshold={min_importance}, 共 {count} 条记忆")
        return count

    def delete_by_pattern(self, pattern: str) -> int:
        """根据文件名模式批量删除记忆"""
        count = 0

        for type_dir in self.base_dir.iterdir():
            if not type_dir.is_dir() or type_dir.name == "memory_index.json":
                continue

            for date_dir in type_dir.iterdir():
                if not date_dir.is_dir():
                    continue

                for file_path in date_dir.glob("*.json"):
                    if pattern in file_path.name:
                        memory = self._load_memory_from_path(file_path)
                        if memory:
                            with self._cache_lock:
                                if memory.id in self._cache:
                                    del self._cache[memory.id]
                            self._remove_from_index(memory.id)
                        file_path.unlink()
                        count += 1
                        logger.info(f"按模式删除: {file_path.name}")

        return count

    def query(self, query: MemoryQuery) -> List[EntityMemory]:
        """语义查询记忆（基于关键词匹配）"""
        results = []
        query_lower = query.query.lower()
        query_words = set(query_lower.split())

        with self._cache_lock:
            for memory in self._cache.values():
                # 类型过滤
                if query.entity_type and memory.entity_type != query.entity_type:
                    continue

                # 重要性过滤
                if memory.importance_score < query.min_importance:
                    continue

                # 标签过滤
                if query.tags and not any(tag in memory.tags for tag in query.tags):
                    continue

                # 关键词匹配
                score = 0.0
                title_lower = memory.title.lower()
                content_lower = memory.content.lower()

                for word in query_words:
                    if word in title_lower:
                        score += 0.5
                    if word in content_lower:
                        score += 0.3

                # 完全匹配
                if query_lower in title_lower:
                    score += 1.0
                if query_lower in content_lower:
                    score += 0.6

                if score > 0:
                    final_score = score * 0.6 + memory.importance_score * 0.4
                    results.append((memory, final_score))

        results.sort(key=lambda x: x[1], reverse=True)
        limited = [r[0] for r in results[:query.limit]]

        logger.info(f"记忆查询: '{query.query}' -> {len(limited)} 条结果")
        return limited

    def search_by_type(self, entity_type: EntityType) -> List[EntityMemory]:
        """按类型搜索"""
        return self.get_by_type(entity_type)

    def search_by_tag(self, tag: str) -> List[EntityMemory]:
        """按标签搜索"""
        with self._cache_lock:
            return [m for m in self._cache.values() if tag in m.tags]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        type_counts = {}
        date_counts = {}
        type_date_counts = {}

        with self._cache_lock:
            for memory in self._cache.values():
                type_name = memory.entity_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

                date_str = memory.created_at.strftime("%Y%m%d")
                date_counts[date_str] = date_counts.get(date_str, 0) + 1

                type_date_key = f"{type_name}/{date_str}"
                type_date_counts[type_date_key] = type_date_counts.get(type_date_key, 0) + 1

        return {
            "total_count": len(self._cache),
            "by_type": type_counts,
            "by_date": dict(sorted(date_counts.items())),
            "by_type_and_date": type_date_counts,
            "storage_path": str(self.base_dir),
            "index_size": len(self._index)
        }

    def list_files_by_pattern(self, pattern: str = "") -> List[Dict[str, Any]]:
        """列出记忆文件（供手动清理参考）"""
        files_info = []

        for type_dir in self.base_dir.iterdir():
            if not type_dir.is_dir() or type_dir.name == "memory_index.json":
                continue

            for date_dir in type_dir.iterdir():
                if not date_dir.is_dir():
                    continue

                for file_path in date_dir.glob("*.json"):
                    if pattern and pattern not in file_path.name:
                        continue

                    files_info.append({
                        "path": str(file_path.relative_to(self.base_dir)),
                        "type_folder": type_dir.name,
                        "date_folder": date_dir.name,
                        "filename": file_path.name,
                        "size": file_path.stat().st_size,
                        "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    })

        # 按路径排序
        files_info.sort(key=lambda x: x["path"])
        return files_info

    def clear_all(self):
        """清空所有记忆"""
        with self._cache_lock:
            self._cache.clear()

        self._index = {}

        if self.base_dir.exists():
            import shutil
            # 删除所有子目录
            for item in self.base_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                elif item.name != "memory_index.json":
                    item.unlink()

            # 删除索引文件
            if self._index_file.exists():
                self._index_file.unlink()

        # 重新创建基础目录
        self.base_dir.mkdir(parents=True, exist_ok=True)

        logger.info("所有实体记忆已清空")

    async def semantic_search(
            self,
            query: str,
            query_embedding: Optional[List[float]] = None,
            limit: int = 10,
            min_similarity: float = 0.3
    ) -> List[Tuple[EntityMemory, float]]:
        """
        语义搜索实体记忆（使用远程 Embedding API）

        Args:
            query: 查询文本
            query_embedding: 预计算的查询向量（可选）
            limit: 返回数量
            min_similarity: 最低相似度阈值

        Returns:
            List[(EntityMemory, similarity_score)]
        """
        from .vector_retriever import get_embedding_client

        client = get_embedding_client()

        if not client.config.api_key:
            logger.warning("Embedding API 未配置，回退到关键词检索")
            return []

        # 获取查询向量
        if query_embedding is None:
            query_embedding = await client.embed(query)

        if query_embedding is None:
            logger.warning("获取查询向量失败")
            return []

        results = []

        with self._cache_lock:
            for memory in self._cache.values():
                # 计算标题的向量相似度
                title_embedding = await client.embed(memory.title)
                title_sim = client.cosine_similarity(query_embedding, title_embedding) if title_embedding else 0.0

                # 计算内容的向量相似度（只取前500字）
                content_text = memory.content[:500]
                content_embedding = await client.embed(content_text)
                content_sim = client.cosine_similarity(query_embedding, content_embedding) if content_embedding else 0.0

                # 综合相似度（标题权重更高）
                sim_score = max(title_sim * 1.2, content_sim)

                if sim_score >= min_similarity:
                    results.append((memory, sim_score))

        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"语义搜索: '{query}' -> {len(results)} 条结果")
        return results[:limit]

    async def hybrid_search(
            self,
            query: str,
            limit: int = 10,
            min_similarity: float = 0.3
    ) -> List[EntityMemory]:
        """
        混合检索：向量检索 + 关键词检索

        Args:
            query: 查询文本
            limit: 返回数量
            min_similarity: 最低相似度阈值

        Returns:
            List[EntityMemory]
        """
        from .vector_retriever import get_embedding_client

        client = get_embedding_client()
        memories_dict = {}  # id -> (memory, score)

        # 1. 向量检索
        if client.config.api_key:
            semantic_results = await self.semantic_search(query, limit=limit * 2, min_similarity=min_similarity)
            for memory, sim_score in semantic_results:
                current_score = memories_dict.get(memory.id, (None, 0))[1]
                memories_dict[memory.id] = (memory, current_score + sim_score * 0.8)
            logger.debug(f"向量检索: {len(semantic_results)} 条")

        # 2. 关键词检索（作为补充）
        keyword_query = MemoryQuery(query=query, limit=limit * 2)
        keyword_results = self.query(keyword_query)

        for memory in keyword_results:
            base_score = 0.3  # 关键词匹配基础分
            current_score = memories_dict.get(memory.id, (None, 0))[1]
            memories_dict[memory.id] = (memory, current_score + base_score)

        logger.debug(f"关键词检索: {len(keyword_results)} 条")

        # 3. 排序
        sorted_results = sorted(memories_dict.values(), key=lambda x: x[1], reverse=True)

        # 4. 限制数量
        return [r[0] for r in sorted_results[:limit]]


# 全局单例
_entity_memory_store: Optional[EntityMemoryStore] = None


def get_entity_memory_store() -> EntityMemoryStore:
    global _entity_memory_store
    if _entity_memory_store is None:
        _entity_memory_store = EntityMemoryStore()
    return _entity_memory_store