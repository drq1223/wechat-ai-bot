"""
情商引擎 - 三层情商策略：情绪感知 → 回复策略 → 润色调整
"""

import re
from dataclasses import dataclass
from typing import Optional

import prompts


@dataclass
class EmotionResult:
    """情绪分析结果"""
    sentiment: str      # 情绪类别: sad/angry/happy/anxious/joking/neutral/love
    intensity: float    # 情绪强度 0.0~1.0
    suggested_tone: str # 建议回复语气


# --- 第一层：情绪感知 ---

# 情绪关键词库
_SAD_KEYWORDS = [
    "难过", "伤心", "心痛", "委屈", "失落", "沮丧", "郁闷", "低落",
    "不开心", "不高兴", "心碎", "崩溃", "绝望", "无助", "孤独",
    "哭", "泪", "呜呜", "唉", "哎", "好累", "疲惫", "失眠",
    "分手", "离别", "怀念", "思念", "想你", "舍不得",
]
_ANGRY_KEYWORDS = [
    "生气", "愤怒", "烦", "恼", "气死", "火大", "受不了", "过分",
    "无语", "崩溃", "离谱", "过分", "凭啥", "凭什么", "混蛋",
    "讨厌", "恶心", "垃圾", "差劲", "坑", "骂", "滚",
]
_HAPPY_KEYWORDS = [
    "开心", "高兴", "快乐", "幸福", "棒", "好耶", "太好了",
    "哈哈", "嘻嘻", "耶", "万岁", "赞", "优秀", "厉害",
    "爽", "美", "妙", "完美", "惊喜", "期待", "好开心",
]
_ANXIOUS_KEYWORDS = [
    "焦虑", "担心", "害怕", "紧张", "不安", "压力", "焦虑",
    "怎么办", "好怕", "恐惧", "忧虑", "纠结", "迷茫",
    "来不及", "来不及了", "来不及了", "要死了", "完了",
]
_JOKING_KEYWORDS = [
    "哈哈哈", "笑死", "逗", "皮", "666", "牛逼", "nb",
    "绝了", "秀", "牛", "服了", "无语子", "离谱",
    "嘻嘻", "嘿嘿", "哈哈", "草", "蚌", "绷不住",
]
_LOVE_KEYWORDS = [
    "喜欢", "爱", "想你", "想念", "关心", "在乎", "心疼",
    "照顾", "陪伴", "温暖", "感动", "谢谢", "感恩", "亲",
    "抱抱", "摸摸", "pat", "❤", "💕", "🥰", "😍",
]

# 表情符号分类
_SAD_EMOJIS = {"😢", "😭", "💔", "😞", "😔", "🥺", "😿", "😩", "😫"}
_ANGRY_EMOJIS = {"😡", "😠", "🤬", "😤", "💢", "🔥"}
_HAPPY_EMOJIS = {"😊", "😄", "😁", "🥰", "😂", "🤣", "😆", "😃", "🎉", "👏"}
_ANXIOUS_EMOJIS = {"😰", "😱", "😨", "😥", "😓", "🥵"}


def _count_keywords(text: str, keywords: list[str]) -> int:
    """统计文本中关键词出现次数"""
    count = 0
    for kw in keywords:
        count += len(re.findall(re.escape(kw), text))
    return count


def _count_emojis(text: str, emoji_set: set[str]) -> int:
    """统计文本中特定类别表情数量"""
    return sum(1 for ch in text if ch in emoji_set)


def _detect_exclamation_intensity(text: str) -> float:
    """通过标点判断情绪强度"""
    # 多个感叹号 → 强情绪
    exclamations = text.count("！") + text.count("!")
    if exclamations >= 3:
        return 0.8
    elif exclamations >= 2:
        return 0.5
    elif exclamations >= 1:
        return 0.3
    return 0.0


def _detect_repetition_intensity(text: str) -> float:
    """通过重复字符判断情绪强度（如'哈哈哈哈'）"""
    # 连续相同字符3个以上
    matches = re.findall(r"(.)\1{2,}", text)
    if len(matches) >= 2:
        return 0.7
    elif len(matches) >= 1:
        return 0.4
    return 0.0


def analyze(text: str) -> EmotionResult:
    """
    分析消息的情绪倾向

    Args:
        text: 用户消息文本

    Returns:
        EmotionResult: 情绪分析结果
    """
    if not text or not text.strip():
        return EmotionResult("neutral", 0.0, "自然亲切")

    text_lower = text.lower()

    # 计算各类情绪得分
    scores = {
        "sad": _count_keywords(text_lower, _SAD_KEYWORDS) * 2 + _count_emojis(text_lower, _SAD_EMOJIS) * 3,
        "angry": _count_keywords(text_lower, _ANGRY_KEYWORDS) * 2 + _count_emojis(text_lower, _ANGRY_EMOJIS) * 3,
        "happy": _count_keywords(text_lower, _HAPPY_KEYWORDS) * 2 + _count_emojis(text_lower, _HAPPY_EMOJIS) * 3,
        "anxious": _count_keywords(text_lower, _ANXIOUS_KEYWORDS) * 2 + _count_emojis(text_lower, _ANXIOUS_EMOJIS) * 3,
        "joking": _count_keywords(text_lower, _JOKING_KEYWORDS) * 2,
        "love": _count_keywords(text_lower, _LOVE_KEYWORDS) * 2,
    }

    # 标点和重复字符增强
    punct_boost = _detect_exclamation_intensity(text_lower)
    repeat_boost = _detect_repetition_intensity(text_lower)

    # 感叹号可能增强happy或angry
    if punct_boost > 0:
        if scores["happy"] > 0:
            scores["happy"] += punct_boost * 3
        elif scores["angry"] > 0:
            scores["angry"] += punct_boost * 3

    # 重复字符增强happy或joking
    if repeat_boost > 0:
        if scores["happy"] > 0 or scores["joking"] > 0:
            scores["happy"] += repeat_boost * 2
            scores["joking"] += repeat_boost * 2

    # 找最高分
    max_sentiment = max(scores, key=scores.get)
    max_score = scores[max_sentiment]

    # 如果最高分太低，判定为neutral
    if max_score < 1:
        max_sentiment = "neutral"
        max_score = 0.0

    # 计算强度 (0~1)
    intensity = min(max_score / 5.0, 1.0)

    # 确定建议语气
    tone_map = {
        "sad": "温柔关怀",
        "angry": "理解认同",
        "happy": "轻松欢快",
        "anxious": "安抚鼓励",
        "joking": "幽默互动",
        "love": "温暖回应",
        "neutral": "自然亲切",
    }
    suggested_tone = tone_map.get(max_sentiment, "自然亲切")

    return EmotionResult(
        sentiment=max_sentiment,
        intensity=intensity,
        suggested_tone=suggested_tone,
    )


# --- 第二层：回复策略 ---

def get_emotion_prompt(emotion: EmotionResult) -> str:
    """
    根据情绪分析结果，返回对应的补充提示词

    Args:
        emotion: 情绪分析结果

    Returns:
        str: 给AI的情绪感知提示
    """
    return prompts.EMOTION_PROMPTS.get(emotion.sentiment, prompts.EMOTION_PROMPTS["neutral"])


# --- 第三层：润色调整 ---

# 一些增加温度的结尾语气词（不总是加，随机选择）
_WARM_ENDINGS = ["呀", "呢", "哦", "哒", "啦", "嘛"]


def polish(text: str, emotion: EmotionResult) -> str:
    """
    润色AI回复，使其更像真人微信消息

    - 去除AI味
    - 控制长度
    - 调整语气
    - 适当添加表情

    Args:
        text: AI原始回复
        emotion: 用户情绪分析结果

    Returns:
        str: 润色后的回复
    """
    from utils import sanitize_message, truncate_message

    # 1. 去AI味
    result = sanitize_message(text)

    # 2. 控制长度
    result = truncate_message(result, max_length=500)

    # 3. 移除Markdown格式（微信不支持）
    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)  # **bold** → bold
    result = re.sub(r"#{1,6}\s*", "", result)           # # 标题 → 移除
    result = re.sub(r"```[\s\S]*?```", "", result)      # 代码块 → 移除
    result = re.sub(r"`(.+?)`", r"\1", result)          # `code` → code
    result = re.sub(r"[-*]\s+", "", result)              # 列表 → 移除
    result = re.sub(r"\d+\.\s+", "", result)             # 编号列表 → 移除

    # 4. 去除过于正式的语气
    result = result.replace("因此", "所以")
    result = result.replace("然而", "不过")
    result = result.replace("此外", "还有")
    result = result.replace("综上所述", "总之")
    result = result.replace("首先", "")
    result = result.replace("其次", "")
    result = result.replace("最后", "")

    # 5. 清理多余空白
    result = re.sub(r"\n{2,}", "\n", result)
    result = result.strip()

    return result
