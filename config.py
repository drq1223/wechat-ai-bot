"""
配置管理模块 - 从 .env 文件加载所有配置项
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# --- AIHubMix API (GLM-4.7 Free) ---
AIHUBMIX_API_KEY = os.getenv("AIHUBMIX_API_KEY", "")
AIHUBMIX_BASE_URL = os.getenv("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1")
AIHUBMIX_MODEL = os.getenv("AIHUBMIX_MODEL", "coding-glm-4.7-free")

# --- 微信公众号 ---
# 公众号测试号/正式号的 AppID 与 AppSecret
WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
# 公众号后台「服务器配置」里自己填的 Token，用于校验微信请求签名
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "")

# --- 本地服务 ---
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))

# --- 机器人行为 ---
MAX_HISTORY_LENGTH = int(os.getenv("MAX_HISTORY_LENGTH", "20"))
REPLY_DELAY_MIN = float(os.getenv("REPLY_DELAY_MIN", "1"))
REPLY_DELAY_MAX = float(os.getenv("REPLY_DELAY_MAX", "3"))
RATE_LIMIT_COOLDOWN = float(os.getenv("RATE_LIMIT_COOLDOWN", "2"))

# --- 联系人控制 ---
_enabled = os.getenv("ENABLED_CONTACTS", "")
ENABLED_CONTACTS = [c.strip() for c in _enabled.split(",") if c.strip()]

_disabled = os.getenv("DISABLED_CONTACTS", "")
DISABLED_CONTACTS = [c.strip() for c in _disabled.split(",") if c.strip()]

ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "")
ENABLE_GROUP_MESSAGE = os.getenv("ENABLE_GROUP_MESSAGE", "false").lower() == "true"

# --- 路径 ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
CONVERSATIONS_DIR = DATA_DIR / "conversations"


def ensure_dirs():
    """确保运行时目录存在"""
    DATA_DIR.mkdir(exist_ok=True)
    CONVERSATIONS_DIR.mkdir(exist_ok=True)


def validate():
    """验证必要配置是否已填写"""
    errors = []
    if not AIHUBMIX_API_KEY or AIHUBMIX_API_KEY == "your_api_key_here":
        errors.append("请在 .env 中设置 AIHUBMIX_API_KEY (从 https://aihubmix.com 控制台获取)")
    if not WECHAT_APPID or WECHAT_APPID == "your_appid_here":
        errors.append("请在 .env 中设置 WECHAT_APPID (公众号后台获取)")
    if not WECHAT_SECRET or WECHAT_SECRET == "your_secret_here":
        errors.append("请在 .env 中设置 WECHAT_SECRET (公众号后台获取)")
    if not WECHAT_TOKEN:
        errors.append("请在 .env 中设置 WECHAT_TOKEN (公众号「服务器配置」里填的 Token，可自定义)")
    if REPLY_DELAY_MIN >= REPLY_DELAY_MAX:
        errors.append("REPLY_DELAY_MIN 必须小于 REPLY_DELAY_MAX")
    return errors
