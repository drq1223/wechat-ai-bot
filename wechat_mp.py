"""
微信公众号协议层

负责：服务器签名校验、XML 消息解析/封装、access_token 管理、客服消息下发。
只做协议相关的事，业务逻辑在 bot.py。
"""

import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional

import aiohttp

import config

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
CUSTOM_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/custom/send"


# --- 签名校验 ---


def check_signature(signature: str, timestamp: str, nonce: str) -> bool:
    """校验微信服务器请求签名（GET 验证和 POST 消息都会带）"""
    if not config.WECHAT_TOKEN:
        return False
    raw = "".join(sorted([config.WECHAT_TOKEN, timestamp or "", nonce or ""]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest() == (signature or "")


# --- XML ---


def parse_message(xml_body: str) -> dict:
    """把微信推送的 XML 解析成扁平字典（CDATA 文本）"""
    data = {}
    try:
        root = ET.fromstring(xml_body)
    except ET.ParseError as e:
        logger.error(f"XML 解析失败: {e}")
        return data
    for child in root:
        data[child.tag] = child.text or ""
    return data


def build_text_reply(to_user: str, from_user: str, content: str) -> str:
    """构造被动回复的 XML（5 秒内返回才有效）"""
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        "</xml>"
    )


# --- 客服消息 ---


class WechatMP:
    """公众号客户端：access_token + 客服消息"""

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_access_token(self, force: bool = False) -> Optional[str]:
        """获取并缓存 access_token（有效期 7200 秒，提前 200 秒刷新）"""
        if not force and self._access_token and time.time() < self._token_expire_at:
            return self._access_token

        if not config.WECHAT_APPID or not config.WECHAT_SECRET:
            logger.error("未配置 WECHAT_APPID / WECHAT_SECRET，无法获取 access_token")
            return None

        session = await self._get_session()
        params = {
            "grant_type": "client_credential",
            "appid": config.WECHAT_APPID,
            "secret": config.WECHAT_SECRET,
        }
        try:
            async with session.get(TOKEN_URL, params=params) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"获取 access_token 失败: {e}")
            return None

        if "access_token" in data:
            self._access_token = data["access_token"]
            self._token_expire_at = time.time() + data.get("expires_in", 7200) - 200
            logger.info("access_token 已获取")
            return self._access_token

        logger.error(f"获取 access_token 失败: {data}")
        return None

    async def send_text(self, openid: str, content: str, retry: bool = True) -> bool:
        """通过客服消息接口主动下发文本

        前提：用户 48 小时内与公众号有过交互（刚发过消息即满足）。
        """
        token = await self.get_access_token()
        if not token:
            return False

        payload = {
            "touser": openid,
            "msgtype": "text",
            "text": {"content": content},
        }
        session = await self._get_session()
        try:
            async with session.post(
                CUSTOM_SEND_URL, params={"access_token": token}, json=payload
            ) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"客服消息发送异常: {e}")
            return False

        errcode = data.get("errcode", 0)
        if errcode == 0:
            return True

        # 40001/42001: token 失效，刷新后重试一次
        if errcode in (40001, 42001) and retry:
            logger.warning(f"access_token 失效({errcode})，刷新后重试")
            await self.get_access_token(force=True)
            return await self.send_text(openid, content, retry=False)

        logger.error(f"客服消息发送失败: {data}")
        return False


# 全局单例
_client: Optional[WechatMP] = None


def get_client() -> WechatMP:
    global _client
    if _client is None:
        _client = WechatMP()
    return _client
