"""
对话记忆 - 按用户存储上下文，支持长对话摘要压缩
"""

import json
import logging
from pathlib import Path
from typing import Optional

import config
from utils import format_contact_id

logger = logging.getLogger(__name__)

# 运行时对话缓存: {contact_id: [messages]}
_cache: dict[str, list[dict]] = {}


def _conversation_path(contact_id: str) -> Path:
    """获取联系人对话文件路径"""
    safe_id = format_contact_id(contact_id, contact_id)
    return config.CONVERSATIONS_DIR / f"{safe_id}.json"


async def load(contact_id: str) -> list[dict]:
    """从磁盘加载对话历史到缓存"""
    path = _conversation_path(contact_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _cache[contact_id] = data
            logger.debug(f"已加载 {contact_id} 的对话历史 ({len(data)} 条)")
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载 {contact_id} 对话历史失败: {e}")
    _cache[contact_id] = []
    return []


async def save(contact_id: str):
    """将缓存中的对话保存到磁盘"""
    if contact_id not in _cache:
        return
    path = _conversation_path(contact_id)
    try:
        config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_cache[contact_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except IOError as e:
        logger.warning(f"保存 {contact_id} 对话历史失败: {e}")


async def get_context(contact_id: str) -> list[dict]:
    """
    获取联系人的对话上下文（用于发送给AI）

    Returns:
        list[dict]: OpenAI格式的消息列表 [{"role": "user/assistant", "content": "..."}]
    """
    if contact_id not in _cache:
        await load(contact_id)

    messages = _cache.get(contact_id, [])

    # 如果超过最大轮数，压缩旧消息
    max_len = config.MAX_HISTORY_LENGTH * 2  # 每轮 = 1条user + 1条assistant
    if len(messages) > max_len:
        messages = await _summarize_and_trim(contact_id, messages, max_len)

    return messages


async def add_message(contact_id: str, role: str, content: str):
    """
    添加一条消息到对话历史

    Args:
        contact_id: 联系人ID
        role: "user" 或 "assistant"
        content: 消息内容
    """
    if contact_id not in _cache:
        await load(contact_id)

    _cache[contact_id].append({
        "role": role,
        "content": content,
    })

    # 异步保存
    await save(contact_id)


async def _summarize_and_trim(
    contact_id: str,
    messages: list[dict],
    max_len: int,
) -> list[dict]:
    """
    压缩过长的对话历史：
    保留最近的消息，将旧消息摘要为一条system消息

    Args:
        contact_id: 联系人ID
        messages: 当前所有消息
        max_len: 最大消息条数

    Returns:
        list[dict]: 压缩后的消息列表
    """
    # 保留最近 2/3 的消息，压缩前 1/3
    keep_start = len(messages) // 3
    old_messages = messages[:keep_start]
    recent_messages = messages[keep_start:]

    # 尝试用AI生成摘要
    summary = await _generate_summary(old_messages)

    if summary:
        compressed = [{
            "role": "system",
            "content": f"[之前的对话摘要] {summary}",
        }]
        result = compressed + recent_messages
    else:
        # 摘要失败，直接截断保留最近的消息
        result = recent_messages[-max_len:]

    _cache[contact_id] = result
    await save(contact_id)

    logger.info(f"已压缩 {contact_id} 的对话历史: {len(messages)} → {len(result)} 条")
    return result


async def _generate_summary(messages: list[dict]) -> Optional[str]:
    """
    调用AI生成对话摘要

    Args:
        messages: 要摘要的消息列表

    Returns:
        Optional[str]: 摘要文本，失败返回None
    """
    if not messages:
        return None

    try:
        from ai_engine import chat
        from prompts import SUMMARIZE_PROMPT

        # 构造摘要请求
        conversation_text = "\n".join(
            f"{'我' if m['role'] == 'assistant' else '对方'}: {m['content']}"
            for m in messages
        )

        result = await chat(
            messages=[
                {"role": "system", "content": SUMMARIZE_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
            temperature=0.3,
            max_tokens=150,
        )
        return result
    except Exception as e:
        logger.warning(f"生成对话摘要失败: {e}")
        return None


async def clear(contact_id: str):
    """清除某联系人的对话历史"""
    _cache[contact_id] = []
    path = _conversation_path(contact_id)
    if path.exists():
        path.unlink()
    logger.info(f"已清除 {contact_id} 的对话历史")


def get_stats() -> dict[str, int]:
    """获取所有联系人的对话统计"""
    return {cid: len(msgs) for cid, msgs in _cache.items() if msgs}
