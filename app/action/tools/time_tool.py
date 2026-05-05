# app/action/tools/time_tool.py
"""时间工具 - 获取当前时间"""

from datetime import datetime
from zoneinfo import ZoneInfo
from loguru import logger
from typing import Optional


async def get_current_time(timezone: str = "Asia/Shanghai", session_id: str = "") -> str:
    """
    获取当前时间

    Args:
        timezone: 时区，默认为 Asia/Shanghai（北京时间）
        session_id: 会话ID（可选）

    Returns:
        str: 格式化的当前时间
    """
    logger.info(f"[会话 {session_id}] 获取当前时间, 时区={timezone}")
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        return now.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.error(f"获取时间失败: {e}")
        return f"获取时间失败: {str(e)}"