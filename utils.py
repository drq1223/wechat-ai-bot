"""
工具函数 - 延迟模拟、频率控制、消息清洗等
"""

import asyncio
import random
import time
import re
from typing import Optional

import config


# --- 频率控制 ---
_last_reply_time: dict[str, float] = {}


def rate_limit_ok(contact_id: str) -> bool:
    """检查该联系人是否过了冷却期，可以回复"""
    now = time.time()
    last = _last_reply_time.get(contact_id, 0)
    if now - last < config.RATE_LIMIT_COOLDOWN:
        return False
    _last_reply_time[contact_id] = now
    return True


# --- 延迟模拟 ---
async def human_delay():
    """模拟人类打字延迟，随机等待一段时间"""
    delay = random.uniform(config.REPLY_DELAY_MIN, config.REPLY_DELAY_MAX)
    await asyncio.sleep(delay)


# --- 联系人权限 ---
def is_contact_enabled(contact_name: str) -> bool:
    """判断联系人是否在自动回复范围内"""
    # 禁用名单优先
    if contact_name in config.DISABLED_CONTACTS:
        return False
    # 如果设置了启用名单，只回复名单内的人
    if config.ENABLED_CONTACTS:
        return contact_name in config.ENABLED_CONTACTS
    return True


def is_admin(contact_name: str) -> bool:
    """判断是否是管理员"""
    return contact_name == config.ADMIN_CONTACT


# --- 消息清洗 ---
# AI 味道重的表达，需要从回复中移除
AI_PATTERNS = [
    r"作为(?:一个|一名)?(?:AI|人工智能|大语言模型|语言模型|助手|智能助手)[，,。.]?\s*",
    r"我是(?:一个|一名)?(?:AI|人工智能|大语言模型|语言模型|助手|智能助手)[，,。.]?\s*",
    r"(?:我|本人)(?:不是|无法|不能|没有)(?:人类|真人|感情|情感|真实)[，,。.]?\s*",
    r"请注意[，,]?\s*",
    r"(?:以上|上述)(?:信息|内容|回答|建议)(?:仅供参考|供参考)[，,。.]?\s*",
    r"如有(?:需要|疑问|问题)[，,]?(?:请|随时)(?:咨询|联系|问我|告诉我)",
    r"希望(?:这|以上|上述)(?:些|个)?(?:信息|回答|建议|内容)(?:能|可以)(?:帮|帮助|对)(?:到你|您|助)",
]


def sanitize_message(text: str) -> str:
    """清洗AI回复，去掉AI味重的表达"""
    result = text.strip()
    for pattern in AI_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    # 清理多余空格和换行
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r" {2,}", " ", result)
    return result.strip()


def truncate_message(text: str, max_length: int = 500) -> str:
    """截断过长的消息，保持像真人的回复长度"""
    if len(text) <= max_length:
        return text
    # 尝试在句号处截断
    truncated = text[:max_length]
    last_punct = max(
        truncated.rfind("。"),
        truncated.rfind("！"),
        truncated.rfind("？"),
        truncated.rfind("…"),
    )
    if last_punct > max_length * 0.6:
        return truncated[: last_punct + 1]
    return truncated + "…"


# --- 情绪相关工具 ---
def estimate_typing_time(text: str) -> float:
    """估算打字时间（秒），用于更真实的延迟"""
    # 假设打字速度 30-50 字/分钟
    char_count = len(text)
    minutes = char_count / random.uniform(30, 50)
    return max(0.5, min(minutes * 60, 8))  # 最少0.5秒，最多8秒


def format_contact_id(name: str, id_str: str) -> str:
    """格式化联系人ID，用于存储"""
    # 用名字做key更可读，去掉特殊字符
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return safe_name if safe_name else id_str
