"""
消息处理核心 - 与具体平台无关的业务逻辑

输入 (user_id, text)，输出要回复的文本；由 main.py 负责实际下发。
"""

import logging
from typing import Optional

import config
from ai_engine import generate_reply
from memory import get_context, add_message
from utils import rate_limit_ok, is_contact_enabled, is_admin

logger = logging.getLogger(__name__)


async def handle_message(user_id: str, text: str) -> Optional[str]:
    """
    处理一条用户消息

    Args:
        user_id: 用户标识（公众号场景即 openid）
        text: 消息文本

    Returns:
        Optional[str]: 要回复的内容；None 表示不回复
    """
    text = (text or "").strip()
    if not text:
        return None

    # --- 1. 权限检查 ---
    if not is_contact_enabled(user_id):
        logger.debug(f"跳过未启用用户: {user_id}")
        return None

    # --- 2. 频率控制 ---
    if not rate_limit_ok(user_id):
        logger.debug(f"频率限制，跳过: {user_id}")
        return "你发的太快啦，我还在想上一句呢～"

    # --- 3. 管理员命令 ---
    if config.ADMIN_CONTACT and is_admin(user_id):
        cmd_result = await _handle_admin_command(text, user_id)
        if cmd_result is not None:
            return cmd_result

    # --- 4. 对话上下文 ---
    history = await get_context(user_id)

    # --- 5. 生成高情商回复 ---
    logger.info(f"收到 [{user_id}] 消息: {text[:50]}...")
    reply = await generate_reply(user_message=text, history=history)

    if not reply:
        return None

    # --- 6. 存储对话 ---
    await add_message(user_id, "user", text)
    await add_message(user_id, "assistant", reply)

    logger.info(f"回复 [{user_id}]: {reply[:50]}...")
    return reply


async def _handle_admin_command(text: str, user_id: str) -> Optional[str]:
    """
    处理管理员命令

    Returns:
        Optional[str]: 命令回复，非命令返回 None
    """
    text = text.strip()

    if text == "/status":
        from memory import get_stats
        stats = get_stats()
        if not stats:
            return "当前没有活跃对话"
        lines = [f"  {name}: {count}条消息" for name, count in stats.items()]
        return "📊 对话统计:\n" + "\n".join(lines)

    elif text == "/clear":
        from memory import clear
        await clear(user_id)
        return "✅ 已清除我们的对话记忆"

    elif text == "/clearall":
        from memory import _cache
        for cid in list(_cache.keys()):
            from memory import clear
            await clear(cid)
        return "✅ 已清除所有对话记忆"

    elif text == "/ping":
        return "🏓 在呢~"

    elif text == "/test":
        from ai_engine import test_connection
        ok = await test_connection()
        return "✅ AIHubMix 连接正常" if ok else "❌ AIHubMix 连接失败"

    return None


def welcome_message() -> str:
    """关注公众号时的欢迎语"""
    return (
        "嗨，终于等到你啦～\n"
        "想聊点什么都可以，开心的事、烦心的事都行，我都在。"
    )
