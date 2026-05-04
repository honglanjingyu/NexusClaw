# app/action/tools/knowledge_tool.py - 重构后
"""知识库工具 - 从记忆模块的知识库检索信息"""

from typing import Optional
from loguru import logger
from datetime import datetime  # 确保这个导入在文件顶部

# 使用记忆模块的长期记忆
from app.memory.long_term_memory import LongTermMemory
from app.memory.milvus_store import MilvusVectorStore

_milvus_store = None
_long_term_memory = None


def get_long_term_memory():
    """获取长期记忆实例（单例）"""
    global _long_term_memory, _milvus_store

    if _long_term_memory is None:
        try:
            _milvus_store = MilvusVectorStore()
            _long_term_memory = LongTermMemory(vector_store=_milvus_store)
            logger.info(f"长期记忆初始化成功")
        except Exception as e:
            logger.error(f"长期记忆初始化失败: {e}")
            _long_term_memory = None
    return _long_term_memory


async def search_knowledge(query: str, top_k: int = 3) -> str:
    """从知识库中搜索相关信息"""
    logger.info(f"知识库搜索: query='{query}', top_k={top_k}")

    long_memory = get_long_term_memory()
    if long_memory is None:
        return "知识库服务不可用，请检查 Milvus 连接配置。"

    try:
        stats = long_memory.get_stats()
        if not stats.get('available', False) or stats.get('num_entities', 0) == 0:
            return "知识库为空，请先上传文档。"

        results = await long_memory.retrieve(query, top_k=top_k, enable_rerank=False)

        if not results:
            return f"未找到与 '{query}' 相关的知识。"

        formatted = []
        for i, item in enumerate(results, 1):
            similarity = item.score * 100
            metadata = item.metadata
            source = metadata.get('_file_name', metadata.get('source', '未知来源'))
            category = metadata.get('category', '未分类')

            formatted.append(
                f"\n【结果 {i}】(相似度: {similarity:.1f}%)\n"
                f"来源: {source}\n"
                f"分类: {category}\n"
                f"内容: {item.content}"
            )

        return f"找到 {len(results)} 条相关知识：\n" + "\n".join(formatted)

    except Exception as e:
        logger.error(f"知识库搜索失败: {e}")
        return f"知识库搜索出错: {str(e)}"


async def search_knowledge_with_filter(
        query: str,
        category: Optional[str] = None,
        top_k: int = 3
) -> str:
    """从知识库中搜索（支持分类过滤）"""
    long_memory = get_long_term_memory()

    if long_memory is None:
        return "知识库服务不可用"

    try:
        # 先多检索一些，然后过滤
        results = await long_memory.retrieve(query, top_k=top_k * 2, enable_rerank=False)

        if category:
            results = [item for item in results if item.metadata.get('category') == category]
            results = results[:top_k]
        else:
            results = results[:top_k]

        if not results:
            filter_msg = f"且分类为 '{category}'" if category else ""
            return f"未找到与 '{query}'{filter_msg} 相关的知识。"

        formatted = []
        for i, item in enumerate(results, 1):
            similarity = item.score * 100
            metadata = item.metadata

            formatted.append(
                f"【结果 {i}】(相似度: {similarity:.1f}%)\n"
                f"来源: {metadata.get('_file_name', metadata.get('source', '未知'))}\n"
                f"分类: {metadata.get('category', '未分类')}\n"
                f"内容: {item.content}"
            )

        return f"找到 {len(results)} 条相关知识：\n\n" + "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"知识库搜索失败: {e}")
        return f"知识库搜索出错: {str(e)}"


async def get_knowledge_stats() -> str:
    """获取知识库统计信息"""
    long_memory = get_long_term_memory()

    if long_memory is None:
        return "知识库服务不可用"

    try:
        stats = long_memory.get_stats()

        if not stats.get('available', False):
            return "知识库尚未初始化。"

        result = f"""
知识库统计信息:
- 集合名称: {stats.get('collection_name', 'N/A')}
- 文档总数: {stats.get('num_entities', 0)}
- Milvus 地址: {stats.get('host', 'N/A')}:{stats.get('port', 'N/A')}
"""
        return result.strip()

    except Exception as e:
        logger.error(f"获取知识库统计失败: {e}")
        return f"获取知识库统计出错: {str(e)}"


async def add_to_knowledge(content: str, category: str = "general", source: str = "user") -> str:
    """添加知识到知识库"""
    long_memory = get_long_term_memory()

    if long_memory is None:
        return "知识库服务不可用"

    try:
        import uuid
        success = await long_memory.add_knowledge(
            content=content,
            metadata={
                "source": source,
                "category": category,
                "timestamp": datetime.now().isoformat()
            }
        )

        if success:
            return f"✅ 知识已成功添加到知识库"
        else:
            return "❌ 添加知识失败"

    except Exception as e:
        logger.error(f"添加知识失败: {e}")
        return f"添加知识出错: {str(e)}"


from datetime import datetime