# 🤖 微信高情商AI智能体

> 微信公众号官方接口 + GLM-4.7，让AI像真人一样自然、有温度地聊天

一个能挂在微信公众号上的 AI 聊天机器人。它不只是"问答机器"——回复前先判断你的情绪，
再决定怎么接话：难过时先共情不讲道理，开玩笑时接梗不端着。

```
我     我今天考试没考好，好难受
机器人 抱抱你🥺 考砸了心里肯定特别不是滋味吧，别急着自责啦，一次考试而已嘛
       想聊聊是哪科吗？说出来可能会好受点
```

**目录**：[快速开始](#-快速开始) · [配置说明](#-配置说明) ·
[情商引擎原理](#-情商引擎原理) · [常见问题](#-常见问题) · [安全须知](#-安全须知)

## ✨ 特性

- **官方接口** - 走公众号官方 API，零封号风险、长期稳定
- **高情商回复** - 三层情商引擎：情绪感知 → 回复策略 → 润色调整
- **对话记忆** - 按用户独立存储上下文，长对话自动摘要压缩
- **情绪感知** - 识别开心/难过/愤怒/焦虑等情绪，自动调整回复风格
- **拟人化** - 去AI味、控制长度、添加语气词
- **GLM-4.7 驱动** - 经 AIHubMix 中转调用，有免费额度

## 🧠 为什么回复是「异步」的

微信的被动回复要求 **5 秒内** 返回，而 GLM-4.7 是思考型模型，实测单次回复要
10~17 秒，`low` 档也压不下来（该模型不支持关闭思考）。

所以流程是：

```
用户发消息 → 立即回 "success"（0.08s）→ 后台慢慢生成 → 用客服消息接口主动推送
```

客服消息要求用户在 48 小时内与公众号有过交互 —— 用户刚发过消息，条件天然满足。

## 🚀 快速开始

### 1. 安装依赖

```bash
cd wechat-ai-bot
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

### 2. 申请公众号测试号

打开 <https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login> 扫码登录，
页面会直接给出 **appID** 和 **appsecret**（测试号免费、个人可申请、无需认证）。

用微信扫描页面上的「测试号二维码」关注它，之后给它发消息即可对话。

### 3. 配置 .env

```bash
cp .env.example .env
```

至少要填这 4 项：

| 变量 | 来源 |
|------|------|
| `AIHUBMIX_API_KEY` | https://aihubmix.com 控制台 |
| `WECHAT_APPID` | 测试号页面上的 appID |
| `WECHAT_SECRET` | 测试号页面上的 appsecret |
| `WECHAT_TOKEN` | 自己随便起一个，下一步要填到公众号后台 |

### 4. 内网穿透

把本机端口暴露成公网 HTTPS 地址，二选一：

```bash
# cpolar（国内，有免费版）
cpolar http 8080

# ngrok
ngrok http 8080
```

拿到一个形如 `https://xxxx.cpolar.cn` 的地址。

### 5. 填写公众号服务器配置

在测试号页面往下的「服务器配置」里填：

- **URL**：`https://xxxx.cpolar.cn/wx`
- **Token**：和第 3 步 `.env` 里的 `WECHAT_TOKEN` **完全一致**

点「提交」，提示配置成功即可。微信会立刻发一个 GET 请求来验证签名。
注意「消息加解密方式」选**明文模式**（本项目未接入 AES 解密）。

### 6. 启动

```bash
python main.py
```

给测试号发条消息，等十几秒就能收到回复。

## ⚙️ 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AIHUBMIX_API_KEY` | (必填) | AIHubMix API密钥 |
| `AIHUBMIX_BASE_URL` | `https://aihubmix.com/v1` | API地址 |
| `AIHUBMIX_MODEL` | `coding-glm-4.7-free` | 模型名称 |
| `WECHAT_APPID` | (必填) | 公众号 appID |
| `WECHAT_SECRET` | (必填) | 公众号 appsecret |
| `WECHAT_TOKEN` | (必填) | 服务器配置 Token，自定义 |
| `SERVER_HOST` | `0.0.0.0` | 监听地址 |
| `SERVER_PORT` | `8080` | 监听端口 |
| `MAX_HISTORY_LENGTH` | `20` | 每用户最大记忆轮数 |
| `RATE_LIMIT_COOLDOWN` | `13` | 同一人最小回复间隔(秒) |
| `ENABLED_CONTACTS` | (空=全部) | 启用自动回复的 openid |
| `DISABLED_CONTACTS` | (空) | 禁用的 openid |
| `ADMIN_CONTACT` | (空) | 管理员 openid |

> 免费版 `coding-glm-4.7-free` 限额：5 次/分钟、500 次/天、100 万 token/天。
> 所以 `RATE_LIMIT_COOLDOWN` 默认 13 秒，换付费模型后可改回 2。
> 注意思考过程也计入 token，一句闲聊实测消耗 200~700 tokens。

## 🎭 情商引擎原理

### 三层架构

```
用户消息 → [第一层: 情绪感知] → [第二层: 回复策略] → [第三层: 润色调整] → 回复
```

**第一层 - 情绪感知：** 分析关键词、表情符号、标点用法、重复字符，
识别 7 种情绪（开心/难过/愤怒/焦虑/玩笑/平淡/好感）并计算强度 (0~1)

**第二层 - 回复策略：** 按情绪选择风格，如难过 → "先共情再安慰，不讲道理"；
开玩笑 → "接梗互动，轻松回应"

**第三层 - 润色调整：** 去除AI味表达、移除 Markdown（微信不支持）、
正式用语改口语（"因此"→"所以"）、控制长度

## 🔧 管理员命令

在公众号里发送（需在 .env 设置 `ADMIN_CONTACT` 为该用户的 openid）：

| 命令 | 说明 |
|------|------|
| `/status` | 查看所有对话统计 |
| `/clear` | 清除当前对话记忆 |
| `/clearall` | 清除所有对话记忆 |
| `/ping` | 测试机器人是否在线 |
| `/test` | 测试AIHubMix API连接 |

## 📁 项目结构

```
wechat-ai-bot/
├── main.py          # 入口 - Quart 服务，接收微信推送
├── wechat_mp.py     # 公众号协议：签名校验、XML解析、客服消息
├── bot.py           # 消息处理核心（平台无关）
├── ai_engine.py     # AIHubMix (GLM-4.7) 调用
├── emotion.py       # 情商引擎
├── memory.py        # 对话记忆
├── prompts.py       # 高情商系统提示词
├── config.py        # 配置管理
├── utils.py         # 工具函数
├── .env.example     # 环境变量模板
└── data/            # 运行时数据 (gitignored)
    └── conversations/  # 对话历史JSON
```

## ❗ 常见问题

**公众号后台提示「配置失败」**
检查 `.env` 的 `WECHAT_TOKEN` 与后台填的是否完全一致；确认服务正在运行、
穿透地址可访问、URL 末尾带了 `/wx`。

**收不到回复**
看终端日志。若显示 `access_token` 报错，多半是 appID/appsecret 填错；
若显示「下发失败」，检查用户是否在 48 小时内发过消息。

**AI 连接失败**
本机如果访问不了 aihubmix.com，启动时带上代理：

```bash
HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=http://127.0.0.1:7890 python main.py
```

（端口换成你自己的代理端口）

## 🔒 安全须知

- 仓库里的 `.env.example` 只是模板，**不要**把真实的 `.env` 提交上来
  （已在 `.gitignore` 中排除）。推送前可用下面的命令确认：

  ```bash
  git check-ignore -v .env        # 有输出才说明被忽略了
  git ls-files | grep -E "^\.env$"  # 不应该有任何输出
  ```

- `data/conversations/` 存的是真实对话记录，同样已排除。
- 如果密钥不小心提交过，**先去控制台作废（revoke）那把 Key**，
  再从提交历史里清理——只删文件是没用的，历史里仍然看得到。

## 📜 许可证

MIT License - 仅供学习和研究使用。详见 [LICENSE](LICENSE)。
