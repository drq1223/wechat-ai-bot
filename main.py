"""
微信高情商AI智能体 - 入口（微信公众号服务器）

启动方式:
    python main.py

需要先把本机的 8080 端口通过内网穿透暴露成公网 URL，
再填到公众号「服务器配置」的 URL 里（如 https://xxx.cpolar.cn/wx）。

管理员命令 (向公众号发送):
    /status   - 查看对话统计
    /clear    - 清除当前对话记忆
    /clearall - 清除所有对话记忆
    /ping     - 测试机器人是否在线
    /test     - 测试AIHubMix API连接
"""

import asyncio
import logging
import sys
from pathlib import Path

# 在导入其他模块前，确保项目目录在 sys.path 中
PROJECT_DIR = Path(__file__).parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from quart import Quart, request  # noqa: E402

import config  # noqa: E402
from bot import handle_message, welcome_message  # noqa: E402
from wechat_mp import check_signature, parse_message, get_client  # noqa: E402

app = Quart(__name__)
logger = logging.getLogger(__name__)

# 保存后台任务引用，避免被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in ("httpx", "httpcore", "openai", "hypercorn.error", "quart.app"):
        logging.getLogger(name).setLevel(logging.WARNING)


def print_banner():
    """打印启动横幅"""
    print(f"""
╔══════════════════════════════════════╗
║     🤖 微信高情商AI智能体             ║
║                                      ║
║     公众号 + GLM-4.7                 ║
║     让AI像真人一样聊天                ║
╚══════════════════════════════════════╝

  回调地址: http://{config.SERVER_HOST}:{config.SERVER_PORT}/wx
""")


def _spawn(coro):
    """把协程丢到后台执行"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _reply(openid: str, content: str):
    """后台：把内容通过客服消息发给用户"""
    try:
        ok = await get_client().send_text(openid, content)
        if not ok:
            logger.error(f"下发失败: {openid}")
    except Exception as e:
        logger.error(f"下发异常: {e}", exc_info=True)


async def _process_text(openid: str, text: str):
    """后台：生成回复并下发"""
    try:
        reply = await handle_message(openid, text)
        if reply:
            await _reply(openid, reply)
    except Exception as e:
        logger.error(f"处理消息异常: {e}", exc_info=True)


@app.route("/wx", methods=["GET"])
async def wx_verify():
    """服务器配置验证（微信带 signature/timestamp/nonce/echostr 来校验）"""
    signature = request.args.get("signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")
    echostr = request.args.get("echostr", "")

    if check_signature(signature, timestamp, nonce):
        logger.info("✅ 服务器验证通过")
        return echostr

    logger.warning("❌ 签名校验失败，请检查 WECHAT_TOKEN 是否与公众号后台一致")
    return "forbidden", 403


@app.route("/wx", methods=["POST"])
async def wx_receive():
    """接收用户消息

    微信要求 5 秒内响应，而思考型模型通常要十几秒，
    所以这里立刻返回 success，真正的回复走后台 + 客服消息下发。
    """
    signature = request.args.get("signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")

    if not check_signature(signature, timestamp, nonce):
        logger.warning("❌ 收到签名不合法的请求")
        return "forbidden", 403

    msg = parse_message((await request.data).decode("utf-8"))
    if not msg:
        return "success"

    if "Encrypt" in msg:
        logger.error(
            "收到加密消息。请在公众号后台把「消息加解密方式」改为明文模式，"
            "或自行接入 EncodingAESKey 解密。"
        )
        return "success"

    openid = msg.get("FromUserName", "")
    msg_type = msg.get("MsgType", "")

    if msg_type == "event":
        if msg.get("Event") in ("subscribe", "SCAN"):
            logger.info(f"新用户关注: {openid}")
            _spawn(_reply(openid, welcome_message()))
        return "success"

    if msg_type == "text":
        content = msg.get("Content", "")
        _spawn(_process_text(openid, content))

    return "success"


@app.route("/health", methods=["GET"])
async def health():
    """健康检查"""
    return "ok"


async def serve():
    from hypercorn.asyncio import serve as hypercorn_serve
    from hypercorn.config import Config as HyperConfig

    hc = HyperConfig()
    hc.bind = [f"{config.SERVER_HOST}:{config.SERVER_PORT}"]
    hc.accesslog = "-"

    try:
        await hypercorn_serve(app, hc)
    finally:
        await get_client().close()


async def main():
    setup_logging()
    print_banner()

    errors = config.validate()
    if errors:
        logger.error("配置错误:")
        for err in errors:
            logger.error(f"  ❌ {err}")
        logger.info("\n请复制 .env.example 为 .env 并填写配置:")
        logger.info("  cp .env.example .env")
        sys.exit(1)

    config.ensure_dirs()

    logger.info("正在初始化...")
    logger.info(f"  AIHubMix 模型: {config.AIHUBMIX_MODEL}")
    logger.info(f"  服务端口: {config.SERVER_PORT}")

    logger.info("测试 AIHubMix API 连接...")
    from ai_engine import test_connection
    if await test_connection():
        logger.info("  ✅ AIHubMix 连接正常")
    else:
        logger.warning("  ⚠️ AIHubMix 连接失败，请检查 API Key")

    logger.info("\n🚀 服务已启动，等待微信推送消息...")
    await serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再见~")
