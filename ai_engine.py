"""
AI引擎 - 调用 AIHubMix (GLM-4.7 Free) 大模型生成回复
"""

import logging
from typing import Optional

from openai import AsyncOpenAI

import config

logger = logging.getLogger(__name__)

# 初始化 AIHubMix 客户端 (OpenAI 兼容接口)
_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    """获取或创建 AIHubMix 客户端"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.AIHUBMIX_API_KEY,
            base_url=config.AIHUBMIX_BASE_URL,
        )
        logger.info(f"AIHubMix 客户端已初始化 (模型: {config.AIHUBMIX_MODEL})")
    return _client


async def _create(messages: list[dict], **kwargs):
    """底层调用，失败时自动降级（去掉网关不支持的采样参数）"""
    client = get_client()
    try:
        return await client.chat.completions.create(
            model=config.AIHUBMIX_MODEL,
            messages=messages,
            **kwargs,
        )
    except Exception as e:
        # 部分模型/网关不接受 temperature 之外的采样参数，降级重试一次
        if any(k in kwargs for k in ("top_p", "frequency_penalty", "presence_penalty")):
            logger.warning(f"采样参数不被支持，降级重试: {e}")
            return await client.chat.completions.create(
                model=config.AIHUBMIX_MODEL,
                messages=messages,
                max_tokens=kwargs.get("max_tokens", 800),
            )
        raise


async def chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 800,
    top_p: float = 0.9,
    frequency_penalty: float = 0.3,
    presence_penalty: float = 0.3,
) -> str:
    """
    调用 GLM-4.7 生成回复

    Args:
        messages: OpenAI格式的消息列表
        temperature: 创造性 (0~2, 越高越随机)
        max_tokens: 最大回复长度 (思考型模型会占用一部分token，故默认给足)
        top_p: 核采样
        frequency_penalty: 频率惩罚 (减少重复)
        presence_penalty: 存在惩罚 (鼓励多样性)

    Returns:
        str: AI回复文本
    """
    try:
        response = await _create(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )

        content = response.choices[0].message.content
        if content:
            content = content.strip()

        # 记录token使用情况
        if response.usage:
            logger.debug(
                f"Token使用: prompt={response.usage.prompt_tokens}, "
                f"completion={response.usage.completion_tokens}, "
                f"total={response.usage.total_tokens}"
            )

        return content or ""

    except Exception as e:
        logger.error(f"AIHubMix API 调用失败: {e}")
        # 返回一个简单的错误提示，不暴露技术细节
        return "嗯…我刚才走神了，你再说一遍？"


async def generate_reply(
    user_message: str,
    history: list[dict],
    emotion_hint: str = "",
) -> str:
    """
    生成完整的高情商回复

    Args:
        user_message: 用户消息
        history: 对话历史
        emotion_hint: 情绪感知提示

    Returns:
        str: 生成并润色后的回复
    """
    from prompts import SYSTEM_PROMPT
    from emotion import analyze, get_emotion_prompt, polish

    # 1. 分析用户情绪
    emotion = analyze(user_message)

    # 2. 构造消息列表
    messages = []

    # 系统提示
    system_content = SYSTEM_PROMPT
    if emotion_hint:
        system_content += f"\n\n---\n{emotion_hint}"
    else:
        # 自动根据情绪添加提示
        emotion_prompt = get_emotion_prompt(emotion)
        system_content += f"\n\n---\n当前对话情境：{emotion_prompt}"

    messages.append({"role": "system", "content": system_content})

    # 对话历史
    messages.extend(history)

    # 当前用户消息
    messages.append({"role": "user", "content": user_message})

    # 3. 调用AI生成
    raw_reply = await chat(messages)

    # 4. 情商润色
    polished_reply = polish(raw_reply, emotion)

    return polished_reply


async def test_connection() -> bool:
    """测试 AIHubMix API 连接是否正常"""
    try:
        # 思考型模型要留足 token，否则思考占满配额后返回空内容
        response = await _create(
            [{"role": "user", "content": "你好"}],
            max_tokens=800,
        )
        return bool(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"AIHubMix 连接测试失败: {e}")
        return False
