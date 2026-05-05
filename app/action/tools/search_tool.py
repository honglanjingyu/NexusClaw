# app/action/tools/search_tool.py
"""网络搜索工具 - 使用 SerpAPI 进行搜索"""

import os
import aiohttp
from typing import Optional, Dict, Any
from loguru import logger
from dotenv import load_dotenv
from pathlib import Path


# 加载环境变量
def load_env():
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
        Path(__file__).parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            return


load_env()


async def web_search(
        query: str,
        num_results: int = 5,
        search_type: str = "search",
        session_id: str = ""
) -> str:
    """
    使用 SerpAPI 进行网络搜索

    Args:
        query: 搜索关键词
        num_results: 返回结果数量，默认5条，最多10条
        search_type: 搜索类型，search(网页搜索)/news(新闻搜索)/image(图片搜索)
        session_id: 会话ID

    Returns:
        str: 格式化的搜索结果
    """
    logger.info(f"[会话 {session_id}] 网络搜索: query='{query}', num_results={num_results}, type={search_type}")

    api_key = os.getenv("SERPAPI_API_KEY")

    if not api_key:
        logger.error("SERPAPI_API_KEY 未配置")
        return "错误: 未配置 SERPAPI_API_KEY，请在 .env 文件中添加该配置"

    num_results = min(num_results, 10)

    try:
        if search_type == "news":
            results = await _search_news(api_key, query, num_results)
        elif search_type == "image":
            results = await _search_images(api_key, query, num_results)
        else:
            results = await _search_web(api_key, query, num_results)

        if not results:
            return f"未找到与 '{query}' 相关的搜索结果"

        return _format_search_results(results, query, search_type)

    except aiohttp.ClientError as e:
        logger.error(f"网络请求失败: {e}")
        return f"网络搜索失败: 网络连接错误 - {str(e)}"
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return f"搜索失败: {str(e)}"


async def web_search_advanced(
        query: str,
        num_results: int = 5,
        site: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        session_id: str = ""
) -> str:
    """
    高级网络搜索（支持站点限制和日期范围）

    Args:
        query: 搜索关键词
        num_results: 返回结果数量
        site: 限制搜索的网站，如 "github.com"
        start_date: 开始日期，格式 "YYYY-MM-DD"
        end_date: 结束日期，格式 "YYYY-MM-DD"
        session_id: 会话ID

    Returns:
        str: 格式化的搜索结果
    """
    logger.info(f"[会话 {session_id}] 高级搜索: query='{query}', site={site}")

    api_key = os.getenv("SERPAPI_API_KEY")

    if not api_key:
        return "错误: 未配置 SERPAPI_API_KEY"

    advanced_query = query
    if site:
        advanced_query += f" site:{site}"

    num_results = min(num_results, 10)

    try:
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": advanced_query,
            "api_key": api_key,
            "num": num_results,
        }

        if start_date:
            params["tbs"] = f"cdr:1,cd_min:{start_date},cd_max:{end_date or start_date}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return f"搜索失败: HTTP {response.status}"

                data = await response.json()

                results = []
                organic_results = data.get("organic_results", [])

                for item in organic_results[:num_results]:
                    results.append({
                        "title": item.get("title", "无标题"),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "无描述"),
                    })

                if not results:
                    return f"未找到与 '{query}' 相关的搜索结果"

                output = [f"🔍 高级搜索结果 - '{query}'"]
                if site:
                    output.append(f"站点限制: {site}")
                output.append(f"共找到 {len(results)} 条结果:\n")

                for i, item in enumerate(results, 1):
                    output.append(f"\n【结果 {i}】{item['title']}")
                    output.append(f"链接: {item['link']}")
                    output.append(f"摘要: {item['snippet'][:200]}...")

                return "\n".join(output)

    except Exception as e:
        logger.error(f"高级搜索失败: {e}")
        return f"搜索失败: {str(e)}"


# 以下辅助函数保持不变
async def _search_web(api_key: str, query: str, num_results: int) -> list:
    """网页搜索"""
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": num_results,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"SerpAPI 返回错误: {response.status}, {error_text}")
                return []

            data = await response.json()
            results = []
            organic_results = data.get("organic_results", [])
            for item in organic_results[:num_results]:
                results.append({
                    "title": item.get("title", "无标题"),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", "无描述"),
                })
            return results


async def _search_news(api_key: str, query: str, num_results: int) -> list:
    """新闻搜索"""
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "tbm": "nws",
        "num": num_results,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return []
            data = await response.json()
            results = []
            news_results = data.get("news_results", [])
            for item in news_results[:num_results]:
                results.append({
                    "title": item.get("title", "无标题"),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", item.get("description", "无描述")),
                    "date": item.get("date", "未知日期"),
                })
            return results


async def _search_images(api_key: str, query: str, num_results: int) -> list:
    """图片搜索"""
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "tbm": "isch",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return []
            data = await response.json()
            results = []
            image_results = data.get("images_results", [])
            for item in image_results[:num_results]:
                results.append({
                    "title": item.get("title", "无标题"),
                    "link": item.get("link", ""),
                    "original": item.get("original", ""),
                    "source": item.get("source", "未知来源"),
                })
            return results


def _format_search_results(results: list, query: str, search_type: str) -> str:
    """格式化搜索结果"""
    if search_type == "image":
        output = [f"🔍 图片搜索结果 - '{query}' (共 {len(results)} 条):\n"]
        for i, item in enumerate(results, 1):
            output.append(f"\n【图片 {i}】")
            output.append(f"标题: {item['title']}")
            output.append(f"来源: {item['source']}")
            output.append(f"链接: {item['link']}")
            if item.get('original'):
                output.append(f"原图: {item['original']}")
    elif search_type == "news":
        output = [f"📰 新闻搜索结果 - '{query}' (共 {len(results)} 条):\n"]
        for i, item in enumerate(results, 1):
            output.append(f"\n【新闻 {i}】{item['title']}")
            output.append(f"日期: {item.get('date', '未知')}")
            output.append(f"链接: {item['link']}")
            output.append(f"摘要: {item['snippet'][:200]}...")
    else:
        output = [f"🔍 搜索结果 - '{query}' (共 {len(results)} 条):\n"]
        for i, item in enumerate(results, 1):
            output.append(f"\n【结果 {i}】{item['title']}")
            output.append(f"链接: {item['link']}")
            output.append(f"摘要: {item['snippet'][:200]}...")

    return "\n".join(output)