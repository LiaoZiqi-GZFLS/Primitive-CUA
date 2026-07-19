# Kimi K2.6 API 参考文档

> **版本**：K2.6  
> **最后更新**：2025年7月  
> **文档来源**：Kimi API 开放平台（https://platform.kimi.com）

---

## 目录

- [1. 概述](#1-概述)
- [2. 模型规格](#2-模型规格)
- [3. 快速开始](#3-快速开始)
- [4. 核心功能](#4-核心功能)
- [5. 思考模式](#5-思考模式)
- [6. 视觉能力](#6-视觉能力)
- [7. 工具调用](#7-工具调用)
- [8. 文件问答](#8-文件问答)
- [9. 产品定价](#9-产品定价)
- [10. 上下文缓存](#10-上下文缓存)
- [11. 错误处理与常见问题](#11-错误处理与常见问题)

---

## 1. 概述

### 1.1 服务地址与兼容性

Kimi 开放平台提供兼容 OpenAI 协议的 HTTP API，服务地址为：

```
https://api.moonshot.cn
```

使用 SDK 时，`base_url` 设置为 `https://api.moonshot.cn/v1`；直接调用 HTTP 端点时，完整路径如 `https://api.moonshot.cn/v1/chat/completions`。

我们的 API 在请求/响应格式上兼容 OpenAI Chat Completions API。这意味着：

- 可以直接使用 OpenAI 官方 SDK（Python / Node.js）
- 支持大多数兼容 OpenAI 的第三方工具和框架（LangChain、Dify、Coze 等）
- 只需将 `base_url` 指向 `https://api.moonshot.cn/v1` 即可切换

> **部分参数为 Kimi 专有扩展：** `thinking` 参数需要通过 SDK 的 `extra_body` 传递；`partial` 是写在 messages 中 assistant 消息上的字段（`"partial": true`），不是顶层请求参数。详见第 5 章"思考模式"和第 4.4 节"Partial Mode"。

### 1.2 认证方式

所有 API 请求需要在 HTTP 头中携带 API Key：

```http
Authorization: Bearer $MOONSHOT_API_KEY
```

API Key 可在 [Kimi 开放平台控制台](https://platform.kimi.com/console/api-keys) 创建和管理。

> **安全提示：** API Key 是敏感信息，请妥善保管。不要在客户端代码、公开仓库或日志中暴露。建议通过环境变量管理。

### 1.3 SDK 安装与初始化

#### Python

```bash
pip install --upgrade 'openai>=1.0'
```

初始化客户端：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.cn/v1",
)
```

#### Node.js

```bash
npm install openai
```

初始化客户端：

```javascript
const OpenAI = require("openai");
const client = new OpenAI({
    apiKey: "$MOONSHOT_API_KEY",
    baseURL: "https://api.moonshot.cn/v1",
});
```

> **环境要求：** Python 版本需 >= 3.7.1，Node.js 版本需 >= 18，OpenAI SDK 版本需 >= 1.0.0。

验证 SDK 版本：

```bash
python -c 'import openai; print("version =", openai.__version__)'
```

#### 通用请求头

| 请求头 | 值 | 说明 |
|--------|------|------|
| Content-Type | application/json | 请求体格式 |
| Authorization | Bearer `$MOONSHOT_API_KEY` | 认证令牌 |

### 1.4 API 端点一览

#### 核心 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 创建对话补全 |
| `/v1/models` | GET | 列出模型 |
| `/v1/tokenizers/estimate-token-count` | POST | 计算 Token |
| `/v1/users/me/balance` | GET | 查询余额 |

#### 文件接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/files` | POST | 上传文件 |
| `/v1/files` | GET | 列出文件 |
| `/v1/files/{file_id}` | GET | 获取文件信息 |
| `/v1/files/{file_id}` | DELETE | 删除文件 |
| `/v1/files/{file_id}/content` | GET | 获取文件内容 |

### 1.5 错误处理

请求失败时返回 JSON 格式的错误响应，包含 `error.type` 和 `error.message` 字段。常见的 HTTP 状态码包括：

- `400` - 请求错误
- `401` - 认证失败
- `429` - 速率限制
- `500` - 服务端错误

完整的错误类型、错误消息和排障建议，请参阅 Kimi 开放平台错误说明文档。

---

## 2. 模型规格

### 2.1 Kimi K2.6 模型介绍

Kimi K2.6 是 Kimi 最新最智能的模型，在 Kimi K2.5 的基础上在智能体编程（agentic coding）、长上下文推理、长周期执行、前端设计场景上有较大的升级。Kimi K2.6 的通用 Agent、代码、视觉理解等综合能力得到全面提升，其中在博士级难度的完整版人类最后的考试（Humanity's Last Exam）、在考察模型真实软件工程能力的 SWE-Bench Pro、评估 Agent 深度检索能力的 DeepSearchQA 等基准测试中均取得行业领先的成绩，同时支持文本、图片与视频输入，思考与非思考模式，对话与 Agent 任务。

Kimi K2.6 作为国内领先的 Coding 模型，在长程代码任务中的表现取得了突破，面对不同编程语言（如 Rust、Go、Python）和任务场景（如前端、运维、性能优化）均具备更可靠的泛化能力。

### 2.2 模型能力与特点

| 能力 | 说明 |
|------|------|
| 文本输入 | 支持 |
| 图片输入 | 支持（详见第 6 章） |
| 视频输入 | 支持（详见第 6 章） |
| 思考模式 | 支持（默认开启，可关闭，详见第 5 章） |
| 工具调用 | 支持（详见第 7 章） |
| JSON Mode | 支持（详见第 4.3 节） |
| Partial Mode | 支持（详见第 4.4 节） |
| 联网搜索 | 支持（详见第 7.5 节） |
| 流式输出 | 支持（详见第 4.2 节） |

### 2.3 上下文窗口

Kimi K2.6 提供 **256K 上下文窗口**（即 262,144 tokens）。以下模型均提供 256K 上下文窗口：

- `kimi-k2.6`
- `kimi-k2.5`
- `kimi-k2.7-code`
- `kimi-k2.7-code-highspeed`

### 2.4 参数默认值与约束

**我们建议用户不要手动设置以下字段，而是使用默认值。**

| 字段 | 是否必须 | 说明 | 类型 | 取值 |
|------|----------|------|------|------|
| `max_tokens` | optional | 聊天完成时生成的最大 token 数。 | int | 默认值为 32k，即 32768 |
| `thinking` | optional | **新增** 该参数控制模型是否启用思考。 | object | 默认值为 `{"type": "enabled"}`。只能为 `{"type": "enabled"}` 或 `{"type": "disabled"}` |
| `temperature` | optional | 使用什么采样温度。 | float | K2.6/K2.5 系列模型将使用确定值 1.0，非思考模式下将使用确认值 0.6。若指定其他值，将会报错。 |
| `top_p` | optional | 采样方法。 | float | K2.6/K2.5 系列模型将使用确定值 0.95。若指定其他值，将会报错。 |
| `n` | optional | 为每条输入消息生成多少个结果。 | int | K2.6/K2.5 系列模型将使用确定值 1。若指定其他值，将会报错。 |
| `presence_penalty` | optional | 存在惩罚。 | float | K2.6/K2.5 系列模型将使用固定值 0.0。若指定其他值，将会报错。 |
| `frequency_penalty` | optional | 频率惩罚。 | float | K2.6/K2.5 系列模型将使用确定值 0.0。若指定其他值，将会报错。 |

#### Tool Use 参数兼容性

当使用工具时，若 `thinking` 设置值为 `{"type": "enabled"}`，请注意，为了确保模型的性能，会有以下约束：

- 为了避免思考内容与指定的 `tool_choice` 冲突，`tool_choice` 只能使用 `"auto"` 和 `"none"`（默认值为 `"auto"`），取任何其他值将会报错；
- 在多步工具调用过程中，您必须在将本轮会话中工具调用时 assistant message 里的 `reasoning_content` 保留在上下文当中，否则会报错；
- 官方内置的 `builtin_function` 的联网搜索 `$web_search` 工具暂时与 Kimi K2.6/Kimi K2.5 思考模式不兼容，可以选择先关闭思考模式后使用联网搜索工具 `$web_search`。

---

## 3. 快速开始

### 3.1 获取 API Key

在使用 Kimi API 之前，你需要先获取一个 API Key。请前往 [Kimi 开放平台控制台](https://platform.kimi.com/console/api-keys) 创建和管理你的 API Key。

### 3.2 第一个 API 调用

以下是使用 Kimi K2.6 进行基础对话的示例：

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "你好！"}
    ]
)

print(completion.choices[0].message.content)
```

### 3.3 图片理解示例

```python
import os
import base64
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

image_path = "kimi.png"
with open(image_path, "rb") as f:
    image_data = f.read()

image_url = f"data:image/{os.path.splitext(image_path)[1].lstrip('.')};base64,{base64.b64encode(image_data).decode('utf-8')}"

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": "请描述图片的内容。"},
            ],
        },
    ],
)

print(completion.choices[0].message.content)
```

### 3.4 视频理解示例

```python
import os
import base64
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

video_path = "kimi.mp4"
with open(video_path, "rb") as f:
    video_data = f.read()

video_url = f"data:video/{os.path.splitext(video_path)[1].lstrip('.')};base64,{base64.b64encode(video_data).decode('utf-8')}"

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": video_url}},
                {"type": "text", "text": "请描述视频的内容。"},
            ],
        },
    ],
)

print(completion.choices[0].message.content)
```

### 3.5 多模态工具能力示例

Kimi K2.6 模型综合了多种能力。以下是一个展示 K2.6 视觉理解+工具调用能力的示例：

```python
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from openai import OpenAI

tools = [{
    "type": "function",
    "function": {
        "name": "watch_video_clip",
        "description": "Watch a video file or a sub-clip of it.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The path to the video file"},
                "start_time": {"type": "number", "description": "Start time in seconds"},
                "end_time": {"type": "number", "description": "End time in seconds"}
            },
            "required": ["path"]
        }
    }
}]

def watch_video_clip(path: str, start_time: float = None, end_time: float = None) -> list[dict]:
    video_path = Path(path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    if start_time is None and end_time is None:
        with open(path, "rb") as f:
            video_base64 = base64.b64encode(f.read()).decode("utf-8")
        return [
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_base64}"}},
            {"type": "text", "text": f"Full video: {video_path.name}"}
        ]

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    start_time = start_time or 0
    end_time = end_time or duration
    clip_duration = end_time - start_time

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
        try:
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(start_time), "-i", path,
                "-t", str(clip_duration), "-c:v", "libx264", "-c:a", "aac",
                "-preset", "fast", "-crf", "23", "-movflags", "+faststart",
                "-loglevel", "error", tmp_path
            ], check=True)
            with open(tmp_path, "rb") as f:
                video_base64 = base64.b64encode(f.read()).decode("utf-8")
            return [
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_base64}"}},
                {"type": "text", "text": f"Clip from {video_path.name}: {start_time}s - {end_time}s"}
            ]
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1"
)

def agent_loop(user_message: str):
    messages = [
        {"role": "system", "content": "You are a video analysis assistant."},
        {"role": "user", "content": user_message}
    ]

    while True:
        response = client.chat.completions.create(
            model="kimi-k2.6",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        message = response.choices[0].message
        messages.append(message.model_dump())

        if not message.tool_calls:
            return message.content

        for tool_call in message.tool_calls:
            if tool_call.function.name == "watch_video_clip":
                args = json.loads(tool_call.function.arguments)
                result = watch_video_clip(**args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

answer = agent_loop("分析 /path/to/test_video.mp4 这个视频的 8-13 秒发生了什么")
print(answer)
```

---


## 4. 核心功能

### 4.1 多轮对话

#### 核心概念

Kimi API 本身不具有记忆功能，它是无状态的。这意味着，当你多次请求 API 时，Kimi 大模型并不知道你前一次请求的内容，也不会记忆任何请求的上下文信息。因此，我们需要手动维护每次请求的上下文（Context），把上一次请求过的内容手动加入到下一次请求中。

#### 基础多轮对话实现

以下代码展示了最基础的多轮对话实现方式，通过维护一个全局的 `messages` 列表来记录对话历史。

**Python：**

```python
from openai import OpenAI

client = OpenAI(
    api_key="MOONSHOT_API_KEY",
    base_url="https://api.moonshot.cn/v1",
)

messages = [
    {
        "role": "system",
        "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"
    }
]

def chat(input: str) -> str:
    global messages
    
    messages.append({"role": "user", "content": input})
    
    completion = client.chat.completions.create(
        model="kimi-k2.6",
        messages=messages
    )
    
    assistant_message = completion.choices[0].message
    messages.append(assistant_message)
    
    return assistant_message.content

print(chat("你好，我今年 27 岁。"))
print(chat("你知道我今年几岁吗？"))
```

**Node.js：**

```javascript
const OpenAI = require("openai");

const client = new OpenAI({
    apiKey: "MOONSHOT_API_KEY",
    baseURL: "https://api.moonshot.cn/v1",
});

let messages = [
    {
        role: "system",
        content: "你是 Kimi，由 Moonshot AI 提供的人工智能助手。",
    },
];

async function chat(input) {
    messages.push({ role: "user", content: input });
    
    const completion = await client.chat.completions.create({
        model: "kimi-k2.6",
        messages: messages
    });
    
    const assistantMessage = completion.choices[0].message;
    messages.push(assistantMessage);
    
    return assistantMessage.content;
}

(async () => {
    console.log(await chat("你好，我今年 27 岁。"));
    console.log(await chat("你知道我今年几岁吗？"));
})();
```

#### 控制上下文长度

随着 `chat` 调用次数的增多，`messages` 列表的长度不断增加，最终可能超过模型支持的上下文窗口大小。推荐只保留最新的 N 条消息作为本次请求的上下文。

**Python：**

```python
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

system_messages = [{"role": "system", "content": "你是 Kimi。"}]
messages = []

def make_messages(input: str, n: int = 20) -> list[dict]:
    global messages
    messages.append({"role": "user", "content": input})
    new_messages = []
    new_messages.extend(system_messages)
    if len(messages) > n:
        messages = messages[-n:]
    new_messages.extend(messages)
    return new_messages

def chat(input: str) -> str:
    completion = client.chat.completions.create(
        model="kimi-k2.6",
        messages=make_messages(input)
    )
    assistant_message = completion.choices[0].message
    messages.append(assistant_message)
    return assistant_message.content
```

**Node.js：**

```javascript
const OpenAI = require("openai");
const client = new OpenAI({ apiKey: "MOONSHOT_API_KEY", baseURL: "https://api.moonshot.cn/v1" });

const systemMessages = [{ role: "system", content: "你是 Kimi。" }];
let messages = [];

async function makeMessages(input, n = 20) {
    messages.push({ role: "user", content: input });
    let newMessages = systemMessages.concat([]);
    if (messages.length > n) {
        messages = messages.slice(-n);
    }
    newMessages = newMessages.concat(messages);
    return newMessages;
}

async function chat(input) {
    const completion = await client.chat.completions.create({
        model: "kimi-k2.6",
        messages: await makeMessages(input)
    });
    const assistantMessage = completion.choices[0].message;
    messages.push(assistantMessage);
    return assistantMessage.content;
}
```

#### 实际业务场景中的考虑因素

- **并发场景**下可能需要额外的读写锁
- 针对**多用户场景**，需要为每个用户单独维护 `messages` 列表
- 你可能需要对 `messages` 列表进行**持久化**
- 你可能仍然需要更精确的方式计算 `messages` 列表中需要保留多少条消息
- 你可能想对被遗弃的消息做一次**总结**，并生成一条新的消息加入到 `messages` 列表中

---

### 4.2 流式输出

#### 如何使用流式输出

流式输出（Streaming）就是每当 Kimi 大模型生成了一定数量的 Tokens 时（通常数量为 1 Token），立刻将这些 Tokens 传输给客户端，而不是等待所有 Tokens 生成完毕后再传输。流式输出能让用户第一时间看到模型输出的第一个 Token，减少等待时间。

通过 `stream=True` 启用流式输出：

**Python：**

```python
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

stream = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"}
    ],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="")
```

**Node.js：**

```javascript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "MOONSHOT_API_KEY", baseURL: "https://api.moonshot.cn/v1" });

const stream = await client.chat.completions.create({
    model: "kimi-k2.6",
    messages: [
        { role: "system", content: "你是 Kimi。" },
        { role: "user", content: "你好，我叫李雷，1+1等于多少？" }
    ],
    stream: true,
});

for await (const chunk of stream) {
    const delta = chunk.choices[0].delta;
    if (delta.content) {
        process.stdout.write(delta.content);
    }
}
```

#### SSE 响应格式

启用流式输出后，响应使用 `Content-Type: text/event-stream`（SSE）。数据块均以 `data:` 为前缀，紧跟一个合法的 JSON 对象，以两个换行符 `\n\n` 结束。所有数据块传输完成后，使用 `data: [DONE]` 标识传输完成。

```
data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k2.6","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k2.6","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

...

data: {"id":"cmpl-xxx","object":"chat.completion.chunk","created":1698999575,"model":"kimi-k2.6","choices":[{"index":0,"delta":{},"finish_reason":"stop","usage":{"prompt_tokens":19,"completion_tokens":13,"total_tokens":32}}]}

data: [DONE]
```

#### Tokens 计算

使用流式输出时，最准确的计算 Tokens 方式是等待所有数据块传输完毕后，通过访问最后一个数据块中的 `usage` 字段来查看。

如果流式输出被中断（网络连接中断等），最后一个数据块可能尚未传输完毕。建议将每个已获取的数据块内容保存下来，在请求结束后使用 Tokens 计算接口计算总消耗量：

```python
import os
import httpx
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

def estimate_token_count(input: str) -> int:
    header = {"Authorization": f"Bearer {os.environ['MOONSHOT_API_KEY']}"}
    data = {"model": "kimi-k2.6", "messages": [{"role": "user", "content": input}]}
    r = httpx.post("https://api.moonshot.cn/v1/tokenizers/estimate-token-count", headers=header, json=data)
    r.raise_for_status()
    return r.json()["data"]["total_tokens"]

stream = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[{"role": "user", "content": "你好"}],
    stream=True,
)

completion = []
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        completion.append(delta.content)

print("completion_tokens:", estimate_token_count("".join(completion)))
```

#### 如何终止输出

直接关闭 HTTP 网络连接，或直接丢弃后续的数据块：

```python
for chunk in stream:
    if condition:
        break
```

#### 不使用 SDK 时处理流式输出

**Python（httpx）：**

```python
import httpx
import json

data = {"model": "kimi-k2.6", "messages": [{"role": "user", "content": "你好"}], "stream": True}
r = httpx.post("https://api.moonshot.cn/v1/chat/completions", json=data)

buffer = ""
for line in r.iter_lines():
    line = line.strip()
    if len(line) == 0:
        chunk = json.loads(buffer)
        choice = chunk["choices"][0]
        delta = choice["delta"]
        content = delta.get("content")
        if content:
            print(content, end="")
        buffer = ""
    elif line.startswith("data: "):
        buffer = line.lstrip("data: ")
        if buffer == "[DONE]":
            break
```

**Node.js（axios/fetch）：**

```javascript
import axios from "axios";

const data = { model: "kimi-k2.6", messages: [{ role: "user", content: "你好" }], stream: true };
const response = await axios.post("https://api.moonshot.cn/v1/chat/completions", data, {
    responseType: "stream",
    headers: { "Authorization": `Bearer ${process.env.MOONSHOT_API_KEY}`, "Content-Type": "application/json" }
});

let buffer = "";
response.data.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") continue;
        if (trimmed.startsWith("data: ")) {
            const content = trimmed.slice(6);
            if (content === "[DONE]") return;
            try {
                const parsed = JSON.parse(content);
                if (parsed.choices[0].delta.content) {
                    process.stdout.write(parsed.choices[0].delta.content);
                }
            } catch (e) {}
        }
    }
});
```

> **重要提示**：请始终使用 `data: [DONE]` 来判断数据是否已传输完成，而不是使用 `finish_reason` 或其他方式。在未接收到 `data: [DONE]` 前，都应视作消息是不完整的。

#### n>1 时的处理

```python
import httpx
import json

data = {"model": "kimi-k2.6", "messages": [{"role": "user", "content": "你好"}], "stream": True, "n": 2}
r = httpx.post("https://api.moonshot.cn/v1/chat/completions", json=data)

messages = [{}, {}]
for line in r.iter_lines():
    line = line.strip()
    if len(line) == 0:
        chunk = json.loads(data)
        for choice in chunk["choices"]:
            index = choice["index"]
            delta = choice["delta"]
            content = delta.get("content")
            if content:
                messages[index]["content"] = messages[index].get("content", "") + content
        data = ""
    elif line.startswith("data: "):
        data = line.lstrip("data: ")
        if data == "[DONE]": break
```

---

### 4.3 JSON Mode

在某些场景下，我们希望模型能以固定格式的 JSON 文档输出内容。使用 `response_format` 参数，将其设置为 `{"type": "json_object"}` 来启用 JSON Mode，Kimi 大模型会输出一个合法的、可被正确解析的 JSON 文档。

#### 使用注意事项

1. 在提示词 system prompt 或 user prompt 中告知 Kimi 大模型应该生成怎样的 JSON 文档，包括具体的字段名称、字段类型等，最好能提供示例；
2. Kimi 大模型只会生成 JSON Object 类型的 JSON 文档，请不要引导模型生成 JSON Array 或其他类型；
3. 如果没有正确告知模型需要输出的 JSON Object 的格式，模型会生成不符合预期的结果。

#### JSON Mode 应用示例

**Python：**

```python
import json
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

system_prompt = """
你是月之暗面（Kimi）的智能客服。请使用如下 JSON 格式输出你的回复：
{
  "text": "文字信息",
  "image": "图片地址",
  "url": "链接地址"
}
"""

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"}
    ],
    response_format={"type": "json_object"},
)

content = json.loads(completion.choices[0].message.content)
print("text:", content.get("text"))
print("image:", content.get("image"))
print("url:", content.get("url"))
```

**Node.js：**

```javascript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "MOONSHOT_API_KEY", baseURL: "https://api.moonshot.cn/v1" });

const system_prompt = `请使用如下 JSON 格式输出你的回复：
{
  "text": "文字信息",
  "image": "图片地址",
  "url": "链接地址"
}`;

const completion = await client.chat.completions.create({
    model: "kimi-k2.6",
    messages: [
        { role: "system", content: "你是 Kimi。" },
        { role: "system", content: system_prompt },
        { role: "user", content: "你好，我叫李雷，1+1等于多少？" }
    ],
    response_format: { type: "json_object" },
});

const content = JSON.parse(completion.choices[0].message.content);
console.log("text:", content.text);
```

#### 不完整的 JSON

如果获取的 JSON 文档不完整或被截断，请检查 `finish_reason` 字段是否为 `length`。较小的 `max_tokens` 值会导致模型输出内容被截断。建议预估输出的 JSON 文档大小后，设置一个合理的 `max_tokens` 值。

---

### 4.4 Partial Mode

Partial Mode 允许 Kimi 大模型顺着给定的语句继续往下说。例如，在客服场景中，希望智能机器人客服每一句的开头都是"尊敬的用户您好"。

#### 基本用法

**Python：**

```python
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "你好？"},
        {
            "partial": True,
            "role": "assistant",
            "content": "尊敬的用户您好，",
        },
    ]
)

print("尊敬的用户您好，" + completion.choices[0].message.content)
```

**Node.js：**

```javascript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "MOONSHOT_API_KEY", baseURL: "https://api.moonshot.cn/v1" });

const completion = await client.chat.completions.create({
    model: "kimi-k2.6",
    messages: [
        { role: "system", content: "你是 Kimi。" },
        { role: "user", content: "你好？" },
        { partial: true, role: "assistant", content: "尊敬的用户您好，" }
    ]
});

console.log("尊敬的用户您好，" + completion.choices[0].message.content);
```

#### 使用要点

1. 在 `messages` 列表尾部添加一条额外的 message，设置 `role=assistant`、`partial=True`
2. 将需要喂给模型的内容放置在 `content` 字段中，模型会强制以该内容开头开始生成回复
3. 将 `content` 拼接到模型生成的内容之前，组成完整回复

#### 续接被截断的输出

当输出因 `max_tokens` 过低被截断时（`finish_reason=length`），可使用 Partial Mode 续接：

```python
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[{"role": "user", "content": "请背诵完整的出师表。"}],
    max_tokens=1200,
)

if completion.choices[0].finish_reason == "length":
    prefix = completion.choices[0].message.content
    reasoning_content = getattr(completion.choices[0].message, "reasoning_content", None)
    print(prefix, end="")
    print("「继续输出--------->」")

    assistant_msg = {
        "role": "assistant",
        "content": prefix,
        "partial": True,
    }
    if reasoning_content:
        assistant_msg["reasoning_content"] = reasoning_content

    completion = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {"role": "user", "content": "请背诵完整的出师表。"},
            assistant_msg
        ],
        max_tokens=86400,
    )
    print(completion.choices[0].message.content)
```

#### Partial Mode 中的 `name` 字段

`name` 字段用于强化模型对角色的认知，强制模型以指定角色的口吻输出内容：

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "下面你扮演凯尔希，请用凯尔希的语气和我对话。凯尔希是手机游戏《明日方舟》中的六星医疗职业医师分支干员。"},
        {"role": "user", "content": "你怎么看待特蕾西娅和阿米娅？"},
        {"partial": True, "role": "assistant", "name": "凯尔希", "content": ""}
    ],
    max_tokens=65536,
)

print(completion.choices[0].message.content)
```

#### 保持角色一致性的技巧

1. **提供清晰的角色描述**：详细介绍个性、背景以及具体特征
2. **增加角色细节**：说话的语气、风格、个性、背景故事和动机
3. **指导在各种情况下如何行动**：在 system prompt 中提供明确的指令
4. **定期使用 system prompt 强化角色设定**：当对话轮次很长时，定期重新注入角色设定

---

### 4.5 response_format 控制（json_schema 模式）

Kimi API 通过 `response_format` 参数约束聊天补全的输出格式，支持两种模式：

| 模式 | type 值 | 说明 | 适用场景 |
|------|---------|------|----------|
| JSON Mode | `json_object` | 保证输出为合法 JSON Object，但不约束具体字段 | 简单 JSON 输出、字段灵活的场景 |
| Structured Output | `json_schema` | 通过 JSON Schema 精确定义字段名、类型、嵌套结构 | 需要严格结构、对接下游系统的场景 |

#### response_format 基本结构

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "schema_name",
        "strict": True,
        "schema": { ... }
    }
}
```

#### 模型差异提示

- **kimi-k2.7-code** 对 Structured Output 的支持最稳，包括嵌套对象、数组、`anyOf` / `oneOf` / `$ref` / `additionalProperties: true` 等都能正常处理。
- **kimi-k2.6** 在复杂 schema 下偶有不稳定表现，例如 `$ref` 可能返回 Markdown 代码块、`oneOf` 可能被忽略、`partial=true` 可能输出 schema 外字段。使用 `kimi-k2.6` 时建议优先使用简单 schema，并在业务层做二次校验。

#### 基本用法示例

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["MOONSHOT_API_KEY"], base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k2.7-code",
    messages=[
        {"role": "system", "content": "你是一个新闻摘要助手。"},
        {"role": "user", "content": "请总结以下新闻：今日，人工智能技术领域迎来重大突破..."}
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "news_summary",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "新闻标题"},
                    "author": {"type": "string", "description": "作者或来源"},
                    "publish_time": {"type": "string", "description": "发布时间"},
                    "summary": {"type": "string", "description": "200 字以内的摘要"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3-5 个关键词"
                    }
                },
                "required": ["title", "author", "summary", "keywords"]
            }
        }
    }
)

import json
result = json.loads(completion.choices[0].message.content)
print(result["title"])
print(result["keywords"])
```

#### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| type | `"json_schema"` or `"json_object"` | 必须设置，二选一 |
| json_schema.name | string | Schema 的标识名称，用于日志和调试 |
| json_schema.strict | boolean | 是否严格按 schema 约束输出。建议显式设置为 `true` |
| json_schema.schema | object | JSON Schema 对象，定义输出结构 |

#### strict 模式说明

`json_schema.strict` 建议设置为 `true`，表示强制模型输出必须完全匹配 schema 定义。此时 schema 需要符合 **MFJS（Moonshot Flavored JSON Schema）** 规范。

- `kimi-k2.7-code` 对 `anyOf` / `oneOf` / `$ref` / `additionalProperties: true` 等特性的支持已比较完善
- `kimi-k2.6` 在复杂 schema 下更可能触碰 MFJS 限制，建议保持 schema 简单

#### 校验 schema 兼容性

```bash
# 安装 walle 工具
go install github.com/moonshotai/walle/cmd/walle@latest

# 校验 schema
walle -schema 'your_schema_json' -level strict
```

#### JSON Mode 与 Structured Output 对比

| 特性 | `json_object` | `json_schema` |
|------|---------------|---------------|
| 输出合法性 | 保证合法 JSON Object | 保证合法 JSON Object |
| 结构约束 | 无（需在 prompt 中描述） | 有（由 schema 严格定义） |
| 字段类型 | 不强制 | 强制匹配 |
| 字段缺失 | 可能缺失字段 | `required` 字段必现 |
| 使用场景 | 简单 JSON 输出 | 需要精确结构的下游系统对接 |
| strict 校验 | 无 | 有（MFJS 规范） |

#### 注意事项

- Schema 需符合 MFJS 规范
- 提示词仍需提供上下文，模型需要理解业务内容
- `additionalProperties: false` 时模型不会输出 schema 中未定义的字段
- `required` 字段在 prompt 中找不到对应信息时，可能返回空字符串
- 当 schema 过于复杂或 prompt 与 schema 矛盾时，可能输出不完整的 JSON

---


## 5. 思考模式

本页涉及以下思考模型：

- **kimi-k2.7-code（最新）**：面向代码场景，**始终开启思考**，且**保留式思考（Preserved Thinking）始终开启**。其高速版 `kimi-k2.7-code-highspeed` 与之为同一模型、思考行为完全一致。
- **kimi-k2.6**：通用思考模型，默认开启思考，可按需关闭，**支持保留式思考**。
- **kimi-k2.5**：通用思考模型，默认开启思考，可按需关闭，但**不支持保留式思考**。

各模型 `thinking` 参数的行为差异如下：

| `thinking` 子字段 | kimi-k2.7-code | kimi-k2.6 | kimi-k2.5 |
|---|---|---|---|
| type（思考开关） | 仅 `"enabled"`，始终思考，传 `"disabled"` 报错 | `"enabled"`（默认）/ `"disabled"` | `"enabled"`（默认）/ `"disabled"` |
| keep（保留式思考） | 不传或传合法值 `"all"` 均按 `"all"` 处理（始终开启、无法关闭） | `null`（默认，不保留）/ `"all"`（启用） | 无此参数，不支持 |

### 5.1 开启与关闭思考

#### 使用 kimi-k2.7-code 模型

`kimi-k2.7-code` 是面向代码场景的最新思考模型，与 `kimi-k2.6` 共享同一套思考机制（`reasoning_content`、多步工具调用、流式输出等），差异仅在 `thinking` 参数。

使用时无需（也不应）传入 `thinking` 参数，只需切换 `model` 即可，模型始终输出 `reasoning_content`。由于保留式思考始终开启，多轮对话中请务必把每一轮历史 assistant 消息的 `reasoning_content` 原样保留在 `messages` 中。

**curl 示例：**

```bash
$ curl https://api.moonshot.cn/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $MOONSHOT_API_KEY" \
    -d '{
        "model": "kimi-k2.7-code",
        "messages": [
            {"role": "system", "content": "你是 Kimi。"},
            {"role": "user", "content": "用 Python 实现快速排序。"}
        ]
    }'
```

**Python 示例：**

```python
import os
import openai

client = openai.Client(
    base_url="https://api.moonshot.cn/v1",
    api_key=os.getenv("MOONSHOT_API_KEY"),
)

stream = client.chat.completions.create(
    model="kimi-k2.7-code",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "用 Python 实现快速排序。"},
    ],
    max_tokens=1024*32,
    stream=True,
)

thinking = False
for chunk in stream:
    if chunk.choices:
        choice = chunk.choices[0]
        if choice.delta and hasattr(choice.delta, "reasoning_content"):
            if not thinking:
                thinking = True
                print("=============开始思考=============")
            print(getattr(choice.delta, "reasoning_content"), end="")
        if choice.delta and choice.delta.content:
            if thinking:
                thinking = False
                print("\n=============思考结束=============")
            print(choice.delta.content, end="")
```

#### 使用 kimi-k2.6 模型

`kimi-k2.6` 是通用思考模型，默认即启用思考能力，因此基本调用无需传入 `thinking` 参数也会输出思考内容。

**curl 示例：**

```bash
$ curl https://api.moonshot.cn/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $MOONSHOT_API_KEY" \
    -d '{
        "model": "kimi-k2.6",
        "messages": [
            {"role": "system", "content": "你是 Kimi。"},
            {"role": "user", "content": "请解释 1+1=2。"}
        ]
    }'
```

**Python 示例：**

```python
import os
import openai

client = openai.Client(
    base_url="https://api.moonshot.cn/v1",
    api_key=os.getenv("MOONSHOT_API_KEY"),
)

stream = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "请解释 1+1=2。"},
    ],
    max_tokens=1024*32,
    stream=True,
)

thinking = False
for chunk in stream:
    if chunk.choices:
        choice = chunk.choices[0]
        if choice.delta and hasattr(choice.delta, "reasoning_content"):
            if not thinking:
                thinking = True
                print("=============开始思考=============")
            print(getattr(choice.delta, "reasoning_content"), end="")
        if choice.delta and choice.delta.content:
            if thinking:
                thinking = False
                print("\n=============思考结束=============")
            print(choice.delta.content, end="")
```

#### 禁用思考能力

对于 `kimi-k2.6`、`kimi-k2.5` 模型，提供禁用思考能力的选项，需要在请求体中指定 `"thinking": {"type": "disabled"}`：

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "model": "kimi-k2.6",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "thinking": {"type": "disabled"}
  }'
```

### 5.2 thinking 参数说明

`kimi-k2.6` 通过 `thinking` 参数控制思考行为，包含两个子字段：

- `thinking.type`：`"enabled"`（默认）| `"disabled"`，控制是否开启思考。
- `thinking.keep`：`null`（默认，忽略历史轮次的思考）| `"all"`（保留历史轮次的 `reasoning_content`，启用保留式思考）。

### 5.3 reasoning_content 读取

在使用 `kimi-k2.7-code`、`kimi-k2.6` 等思考模型（启用思考能力时）时，API 响应中使用了 `reasoning_content` 字段作为模型思考内容的载体：

- openai SDK 中的 `ChoiceDelta` 和 `ChatCompletionMessage` 类型并不提供 `reasoning_content` 字段，因此无法直接通过 `.reasoning_content` 的方式访问该字段，仅支持通过 `hasattr(obj, "reasoning_content")` 来判断是否存在字段，如果存在，则使用 `getattr(obj, "reasoning_content")` 获取字段值
- 如果使用其他框架或自行通过 HTTP 接口对接，可以直接获取与 `content` 字段同级的 `reasoning_content` 字段
- 在流式输出（`stream=True`）的场合，`reasoning_content` 字段一定会先于 `content` 字段出现，可以通过判断是否出现 `content` 字段来识别思考内容是否结束
- `reasoning_content` 中包含的 Tokens 也受 `max_tokens` 参数控制，`reasoning_content` 的 Tokens 数加上 `content` 的 Tokens 数应小于等于 `max_tokens`

### 5.4 多步工具调用

`kimi-k2.7-code` 和 `kimi-k2.6`（启用思考能力时）都支持通过深度推理进行多步工具调用，进而完成非常复杂的任务。

#### 使用须知

为确保最佳效果，使用时请务必按以下方式配置调用：

- **单轮任务内**（一次工具调用循环中产生的多步推理）应保留上下文中所有的思考内容（`reasoning_content` 字段）并随请求回传；跨轮对话是否保留历史思考由 `thinking.keep` 控制（`kimi-k2.6` 默认 `null` 不保留，`kimi-k2.7-code` 始终保留）
- 设置 `max_tokens >= 16000` 以避免无法输出完整的 `reasoning_content` 和 `content`
- **无需设置 `temperature`**，`kimi-k2.7-code`、`kimi-k2.6` 的 `temperature` 不可修改
- 使用流式输出（`stream=True`）：思考模型的输出内容包含了 `reasoning_content`，相比普通模型其输出内容更多，启用流式输出能获得更好的用户体验，同时一定程度避免网络超时问题

#### 完整示例

下面的示例展示了一个"今日新闻报告生成"的场景，模型会依次调用 `date`（获取日期）和 `web_search`（搜索今日新闻）等官方工具：

```python
import os
import json
import httpx
import openai


class FormulaChatClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.openai = openai.Client(base_url=base_url, api_key=api_key)
        self.httpx = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self.model = "kimi-k2.6"

    def get_tools(self, formula_uri: str):
        response = self.httpx.get(f"/formulas/{formula_uri}/tools")
        response.raise_for_status()
        try:
            return response.json().get("tools", [])
        except json.JSONDecodeError as e:
            print(f"错误: 无法解析响应为 JSON")
            raise

    def call_tool(self, formula_uri: str, function: str, args: dict):
        response = self.httpx.post(
            f"/formulas/{formula_uri}/fibers",
            json={"name": function, "arguments": json.dumps(args)},
        )
        response.raise_for_status()
        fiber = response.json()
        if fiber.get("status", "") == "succeeded":
            return fiber["context"].get("output") or fiber["context"].get("encrypted_output")
        if "error" in fiber:
            return f"Error: {fiber['error']}"
        return "Error: Unknown error"

    def close(self):
        self.httpx.close()


base_url = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
api_key = os.getenv("MOONSHOT_API_KEY")
client = FormulaChatClient(base_url, api_key)

formula_uris = ["moonshot/date:latest", "moonshot/web-search:latest"]

all_tools = []
tool_to_uri = {}
for uri in formula_uris:
    try:
        tools = client.get_tools(uri)
        for tool in tools:
            func = tool.get("function")
            if func:
                func_name = func.get("name")
                if func_name:
                    tool_to_uri[func_name] = uri
                    all_tools.append(tool)
    except Exception as e:
        print(f"警告: 加载工具 {uri} 失败: {e}")
        continue

messages = [
    {
        "role": "system",
        "content": "你是 Kimi，一个专业的新闻分析师。",
    },
]

user_request = "请帮我生成一份今日新闻报告，包含重要的科技、经济和社会新闻。"
messages.append({"role": "user", "content": user_request})

max_iterations = 10
for iteration in range(max_iterations):
    try:
        completion = client.openai.chat.completions.create(
            model=client.model,
            messages=messages,
            max_tokens=1024 * 32,
            tools=all_tools,
        )
    except Exception as e:
        print(f"调用模型时发生错误: {e}")
        raise

    message = completion.choices[0].message

    if hasattr(message, "reasoning_content"):
        print(f"=============第 {iteration + 1} 轮思考=============")
        reasoning = getattr(message, "reasoning_content")
        if reasoning:
            print(reasoning[:500] + "..." if len(reasoning) > 500 else reasoning)
        print(f"=============第 {iteration + 1} 轮思考结束=============\n")

    messages.append(message)

    if not message.tool_calls:
        print("=============最终回答=============")
        print(message.content)
        break

    for tool_call in message.tool_calls:
        func_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        formula_uri = tool_to_uri.get(func_name)
        if not formula_uri:
            print(f"错误: 找不到工具 {func_name} 对应的 Formula URI")
            continue
        result = client.call_tool(formula_uri, func_name, args)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": func_name,
            "content": result
        })

print("\n对话完成！")
client.close()
```

### 5.5 保留式思考（Preserved Thinking）

#### 工作原理

保留式思考指在多轮对话中，把历史轮次（previous turns）的 `reasoning_content` 一并透传给模型，让模型在本轮推理时能延续之前的思考脉络。

对于 `kimi-k2.6` 模型，可通过请求体中的 `thinking.keep` 参数控制是否保留历史思考：

| 取值 | 行为 |
|---|---|
| `null` / 不传（默认） | 忽略历史轮次的 `reasoning_content`，上下文更短、成本更低 |
| `"all"` | 完整保留历史轮次的 `reasoning_content`，启用保留式思考 |

`thinking.keep` 只影响历史轮次的 `reasoning_content`，并不改变模型在当前轮次是否产生/输出思考内容（该行为由 `thinking.type` 控制）。推荐把 `keep: "all"` 与 `type: "enabled"` 搭配使用。

对 `kimi-k2.7-code`，保留式思考始终开启、无法关闭。

#### 使用方式

使用 `keep: "all"` 时，需要把每一轮历史 assistant 消息中的 `reasoning_content` 原样保留在 `messages` 中。最简单的做法是把上一轮 API 返回的 assistant message 直接 append 回 `messages`。

**curl 示例：**

```bash
$ curl https://api.moonshot.cn/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $MOONSHOT_API_KEY" \
    -d '{
        "model": "kimi-k2.6",
        "messages": [
            {"role": "system", "content": "你是 Kimi。"},
            {"role": "user", "content": "第一个问题..."},
            {
                "role": "assistant",
                "reasoning_content": "<上一轮 API 返回的 reasoning_content>",
                "content": "<上一轮 API 返回的最终回答>"
            },
            {"role": "user", "content": "请基于之前的分析继续推导下一步。"}
        ],
        "thinking": {"type": "enabled", "keep": "all"}
    }'
```

**Python 示例：**

```python
import os
import openai

client = openai.Client(
    base_url="https://api.moonshot.cn/v1",
    api_key=os.getenv("MOONSHOT_API_KEY"),
)

messages = [
    {"role": "system", "content": "你是 Kimi。"},
    {"role": "user", "content": "第一个问题..."},
    {
        "role": "assistant",
        "reasoning_content": "<上一轮 API 返回的 reasoning_content>",
        "content": "<上一轮 API 返回的最终回答>",
    },
    {"role": "user", "content": "请基于之前的分析继续推导下一步。"},
]

response = client.chat.completions.create(
    model="kimi-k2.6",
    messages=messages,
    stream=True,
    extra_body={"thinking": {"type": "enabled", "keep": "all"}},
)
```

> **注意**：`reasoning_content` 会计入 token 消耗。开启保留式思考后，历史思考内容会持续占用上下文长度并计费，请酌情使用。

---

## 6. 视觉能力

Kimi 视觉模型（包括 `moonshot-v1-8k-vision-preview` / `moonshot-v1-32k-vision-preview` / `moonshot-v1-128k-vision-preview` / `kimi-k2.5` / `kimi-k2.6` / `kimi-k2.7-code` / `kimi-k2.7-code-highspeed`）能够理解视觉内容，包括图片文字、图片颜色和物体形状等内容。最新的 `kimi-k2.6`、`kimi-k2.7-code` 和 `kimi-k2.7-code-highspeed` 模型还能理解视频内容。

### 6.1 图片理解（base64 上传）

```python
import os
import base64
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

image_path = "kimi.png"
with open(image_path, "rb") as f:
    image_data = f.read()

image_url = f"data:image/{os.path.splitext(image_path)[1].lstrip('.' )};base64,{base64.b64encode(image_data).decode('utf-8')}"

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": "请描述图片的内容。"},
            ],
        },
    ],
)

print(completion.choices[0].message.content)
```

> **重要**：在使用 Vision 模型时，`message.content` 字段的类型由 `string` 变更为 `array[object]`。**请不要将 JSON 数组序列化后以 `string` 的格式放入 `message.content` 中**，这样会导致 Kimi 无法正确识别图片类型，并可能引发 `Your request exceeded model token limit` 错误。

**正确格式：**

```json
{
    "model": "kimi-k2.6",
    "messages": [
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
                {"type": "text", "text": "请描述这个图片"}
            ]
        }
    ]
}
```

**错误格式：**

```json
{
    "model": "kimi-k2.6",
    "messages": [
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": "[{\"type\": \"image_url\", ...}]"
        }
    ]
}
```

### 6.2 视频理解

视频理解与图片理解的格式类似，只需将 `image_url` 替换为 `video_url`：

```python
import os
import base64
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

video_path = "kimi.mp4"
with open(video_path, "rb") as f:
    video_data = f.read()

video_url = f"data:video/{os.path.splitext(video_path)[1].lstrip('.' )};base64,{base64.b64encode(video_data).decode('utf-8')}"

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": video_url}},
                {"type": "text", "text": "请描述视频的内容。"},
            ],
        },
    ],
)

print(completion.choices[0].message.content)
```

### 6.3 使用已上传的文件

对于非常大的视频，推荐先上传文件然后通过文件 ID 引用：

```python
import os
from pathlib import Path
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)

video_path = "video.mp4"
file_object = client.files.create(file=Path(video_path), purpose="video")

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": f"ms://{file_object.id}"}},
                {"type": "text", "text": "请描述这个视频"}
            ]
        }
    ]
)

print(completion.choices[0].message.content)
```

注意 `video_url.url` 的格式为 `ms://<file-id>`，ms 为 moonshot storage 的缩写，这是 Moonshot 内部引用文件的协议。

### 6.4 支持的格式与限制

#### 图片支持格式

| 格式 |
|------|
| png |
| jpeg |
| webp |
| gif |

#### 视频支持格式

| 格式 |
|------|
| mp4 |
| mpeg |
| mov |
| avi |
| x-flv |
| mpg |
| webm |
| wmv |
| 3gpp |

#### 功能限制

- **URL 格式的图片：不支持**，目前仅支持使用 base64 编码的图片内容
- **图片数量**：Vision 模型没有图片数量限制，但请确保请求的 Body 大小不超过 100M

### 6.5 分辨率与最佳实践

#### 分辨率建议

- 推荐图片分辨率不超过 **4K (4096*2160)**
- 推荐视频分辨率不超过 **1080p (1920*1080)**
- 再高的分辨率只会增加处理时间，也不会对模型理解的效果有提升

#### 上传文件还是 base64

- 由于请求体的整体大小有限制，所以对于**非常大的视频，必须使用上传文件**的方式使用视觉理解功能
- 对于需要**多次引用**的图片或视频，推荐使用**文件上传**的方式使用视觉理解功能
- 关于上传文件的限制，请参阅第 8 章"文件问答"

#### Tokens 计算及费用

图片与视频进行动态 token 计算，可以通过计算 token 接口，在开始理解前获取包含图片或视频的请求的 token 消耗。

一般说来，图片分辨率越高，消耗的 token 越多；视频由若干张关键帧组成，关键帧的数量越多，分辨率越高，则 token 消耗越多。

Vision 模型在计费方式上与 `moonshot-v1` 系列模型保持一致，根据模型推理的总 Tokens 计费。

---


## 7. 工具调用

工具调用，即 `tool_calls`，由函数调用（即 `function_call`）进化而来。在某些特定的语境下，也可以将工具调用 `tool_calls` 与函数调用 `function_call` 划等号，函数调用 `function_call` 是工具调用 `tool_calls` 的子集。

### 7.1 工具调用基础

工具调用 `tool_calls` 给予了 Kimi 大模型执行具体动作的能力。Kimi 大模型能进行对话聊天并回答用户提出的问题，这是"说"的能力，而通过工具调用 `tool_calls`，Kimi 大模型也拥有了"做"的能力。

一次工具调用 `tool_calls` 包含了以下若干步骤：

1. 使用 JSON Schema 格式定义工具
2. 通过 `tools` 参数将定义好的工具提交给 Kimi 大模型，可以一次性提交多个工具
3. Kimi 大模型会根据当前聊天的上下文，决定使用哪个或哪几个工具，也可以选择不使用工具
4. Kimi 大模型会将调用工具所需要的参数和信息通过 JSON 格式输出
5. 使用 Kimi 大模型输出的参数，执行对应的工具，并将工具执行结果提交给 Kimi 大模型
6. Kimi 大模型根据工具执行结果，给予用户回复

### 7.2 定义与注册工具

#### 定义工具

使用 JSON Schema 格式定义工具：

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": """
                通过搜索引擎搜索互联网上的内容。
                当你的知识无法回答用户提出的问题，或用户请求你进行联网搜索时，调用此工具。
                搜索结果包含网站的标题、网站的地址（URL）以及网站简介。
            """,
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户搜索的内容，请从用户的提问或聊天上下文中提取。"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crawl",
            "description": "根据网站地址（URL）获取网页内容。",
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "需要获取内容的网站地址（URL）。"
                    }
                }
            }
        }
    }
]
```

固定格式：

```json
{
    "type": "function",
    "function": {
        "name": "NAME",
        "description": "DESCRIPTION",
        "parameters": {
            "type": "object",
            "properties": { }
        }
    }
}
```

#### 注册工具

通过 `tools` 参数将定义好的工具提交给模型：

```python
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "请联网搜索 Context Caching，并告诉我它是什么。"}
    ],
    tools=tools,
)

print(completion.choices[0].model_dump_json(indent=4))
```

当模型决定调用工具时，返回内容类似：

```json
{
    "finish_reason": "tool_calls",
    "message": {
        "content": "",
        "role": "assistant",
        "tool_calls": [
            {
                "id": "search:0",
                "function": {
                    "arguments": "{\n  \"query\": \"Context Caching\"\n}",
                    "name": "search"
                },
                "type": "function"
            }
        ]
    }
}
```

注意 `finish_reason` 的值为 `tool_calls`，这意味着本次请求返回的不是模型的回复，而是模型选择执行工具。`tool_calls` 字段是一个列表，表明**模型可以一次性选择多个工具进行调用**。

### 7.3 执行工具

Kimi 大模型并不会帮我们执行工具，需要由我们在接收到模型生成的参数后自行执行：

```python
import httpx
from typing import List, Dict, Any

def search_impl(query: str) -> List[Dict[str, Any]]:
    r = httpx.get("https://your.search.api", params={"query": query})
    return r.json()

def search(arguments: Dict[str, Any]) -> Any:
    query = arguments["query"]
    result = search_impl(query)
    return {"result": result}

def crawl_impl(url: str) -> str:
    r = httpx.get(url)
    return r.text

def crawl(arguments: dict) -> str:
    url = arguments["url"]
    content = crawl_impl(url)
    return {"content": content}

tool_map = {"search": search, "crawl": crawl}

messages = [
    {"role": "system", "content": "你是 Kimi。"},
    {"role": "user", "content": "请联网搜索 Context Caching，并告诉我它是什么。"}
]

finish_reason = None
while finish_reason is None or finish_reason == "tool_calls":
    completion = client.chat.completions.create(
        model="kimi-k2.6", messages=messages, tools=tools,
    )
    choice = completion.choices[0]
    finish_reason = choice.finish_reason
    message = choice.message
    messages.append(message)

    if finish_reason == "tool_calls":
        for tool_call in message.tool_calls:
            tool_call_id = tool_call.id
            tool_call_name = tool_call.function.name
            tool_call_arguments = json.loads(tool_call.function.arguments)
            tool_function = tool_map.get(tool_call_name)
            if tool_function:
                tool_result = tool_function(tool_call_arguments)
            else:
                tool_result = {"error": f"Tool {tool_call_name} not found"}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(tool_result, ensure_ascii=False)
            })

print(message.content)
```

#### 关于 content

在使用工具调用 `tool_calls` 的过程中，在 `finish_reason=tool_calls` 的情况下，偶尔会出现 `message.content` 字段不为空的情况，通常这里的 `content` 内容是模型在解释当前需要调用哪些工具和为什么需要调用这些工具。

#### 关于消息布局

在使用工具调用的场景下，消息排布会变成：

```
system: ...
user: ...
assistant: ...  (包含 tool_calls)
tool: ...
tool: ...
assistant: ...
```

需要注意的是，当模型生成了 `tool_calls` 时，请确保每一个 `tool_call` 都有对应的 `role=tool` 的 message，并且这条 message 设置了正确的 `tool_call_id`。

#### 如果你遇到 tool_call_id not found 错误

如果你遇到 `tool_call_id not found` 错误，可能是由于你未将 Kimi API 返回的 `role=assistant` 消息添加到 messages 列表中。正确的消息序列应该包含 assistant message（含 tool_calls）后紧跟对应的 tool messages。

### 7.4 流式输出中的工具调用

在流式输出模式（stream）下，`tool_calls` 同样适用，但有一些需要额外注意的地方：

1. 在流式输出的过程中，由于 `finish_reason` 将会在最后的数据块中出现，因此建议使用 `delta.tool_calls` 字段是否存在来判断当前回复是否包含工具调用
2. 在流式输出的过程中，会先输出 `delta.content`，再输出 `delta.tool_calls`，因此必须等待 `delta.content` 输出完成后，才能判断和识别 `tool_calls`
3. 在流式输出的过程中，会在最初的数据块中指明当前调用 `tool_calls` 的 `tool_call.id` 和 `tool_call.function.name`，在后续数据块中只输出 `tool_call.function.arguments`
4. 如果模型一次性返回多个 `tool_calls`，会使用 `index` 字段来标识当前 `tool_call` 的索引

**Python（不使用 SDK）：**

```python
import os
import json
import httpx

tools = [{"type": "function", "function": {"name": "search", ...}}]

header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {os.environ.get('MOONSHOT_API_KEY')}",
}

data = {
    "model": "kimi-k2.6",
    "messages": [{"role": "user", "content": "请联网搜索 Context Caching 技术。"}],
    "stream": True,
    "tools": tools,
}

r = httpx.post("https://api.moonshot.cn/v1/chat/completions", headers=header, json=data)

messages = [{}, {}]
for line in r.iter_lines():
    if line.startswith("data: "):
        data_str = line.lstrip("data: ")
        if data_str == "[DONE]": break
        data_json = json.loads(data_str)
        for choice in data_json.get("choices", []):
            delta = choice.get("delta", {})
            choice_index = choice.get("index", 0)
            message = messages[choice_index]

            delta_content = delta.get("content")
            if delta_content:
                message["content"] = message.get("content", "") + delta_content

            tool_calls = delta.get("tool_calls")
            if tool_calls:
                if "tool_calls" not in message:
                    message["tool_calls"] = []
                for tool_call in tool_calls:
                    tool_call_index = tool_call.get("index")
                    if len(message["tool_calls"]) < (tool_call_index + 1):
                        message["tool_calls"].extend([{}] * (tool_call_index + 1 - len(message["tool_calls"])))
                    tool_call_object = message["tool_calls"][tool_call_index]
                    if tool_call.get("id"):
                        tool_call_object["id"] = tool_call["id"]
                    if tool_call.get("type"):
                        tool_call_object["type"] = tool_call["type"]
                    tool_call_function = tool_call.get("function", {})
                    if tool_call_function:
                        if "function" not in tool_call_object:
                            tool_call_object["function"] = {}
                        if tool_call_function.get("name"):
                            tool_call_object["function"]["name"] = tool_call_function["name"]
                        if tool_call_function.get("arguments"):
                            tool_call_object["function"]["arguments"] = tool_call_object["function"].get("arguments", "") + tool_call_function["arguments"]
```

**Python（使用 OpenAI SDK）：**

```python
from openai import OpenAI
import json

client = OpenAI(api_key=os.environ.get("MOONSHOT_API_KEY"), base_url="https://api.moonshot.cn/v1")

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=[{"role": "user", "content": "请联网搜索 Context Caching 技术。"}],
    stream=True,
    tools=tools,
)

messages = [{}, {}]
for chunk in completion:
    for choice in chunk.choices:
        choice_index = choice.index
        message = messages[choice_index]
        delta = choice.delta

        if delta.content:
            message["content"] = message.get("content", "") + delta.content

        if delta.tool_calls:
            if "tool_calls" not in message:
                message["tool_calls"] = []
            for tool_call in delta.tool_calls:
                tool_call_index = tool_call.index
                if len(message["tool_calls"]) < (tool_call_index + 1):
                    message["tool_calls"].extend([{}] * (tool_call_index + 1 - len(message["tool_calls"])))
                tool_call_object = message["tool_calls"][tool_call_index]
                if tool_call.id:
                    tool_call_object["id"] = tool_call.id
                if tool_call.type:
                    tool_call_object["type"] = tool_call.type
                if tool_call.function:
                    if "function" not in tool_call_object:
                        tool_call_object["function"] = {}
                    if tool_call.function.name:
                        tool_call_object["function"]["name"] = tool_call.function.name
                    if tool_call.function.arguments:
                        tool_call_object["function"]["arguments"] = tool_call_object["function"].get("arguments", "") + tool_call.function.arguments
```

#### 关于 tool_calls 和 function_call

`tool_calls` 是 `function_call` 的进阶版。相比于 `function_call`，`tool_calls` 有以下几个优点：

- **支持并行调用**，模型可以一次返回多个 `tool_calls`
- 对于没有依赖关系的 `tool_calls`，模型也会倾向于并行调用，一定程度上降低了 Tokens 消耗

#### 关于 Tokens

`tools` 参数中的内容也会被计算在总 Tokens 中，请确保 `tools`、`messages` 中的 Tokens 总数合计不超过模型的上下文窗口大小。

### 7.5 联网搜索（$web_search）

`$web_search` 是 Kimi 内置的函数，其由 Kimi 大模型定义，也由 Kimi 大模型执行。

#### $web_search 声明

与普通 tool 不同，`$web_search` 不需要提供具体的参数说明：

```python
tools = [
    {
        "type": "builtin_function",
        "function": {"name": "$web_search"},
    },
]
```

`$web_search` 以美元符号 `$` 作为前缀，这是约定的表示 Kimi 内置函数的表达方式。

#### $web_search 执行示例

```python
import os
import json
from typing import Dict, Any
from openai import OpenAI
from openai.types.chat.chat_completion import Choice

client = OpenAI(base_url="https://api.moonshot.cn/v1", api_key=os.environ.get("MOONSHOT_API_KEY"))

def search_impl(arguments: Dict[str, Any]) -> Any:
    return arguments

def chat(messages) -> Choice:
    completion = client.chat.completions.create(
        model="kimi-k2.6",
        messages=messages,
        max_tokens=32768,
        extra_body={"thinking": {"type": "disabled"}},
        tools=[{"type": "builtin_function", "function": {"name": "$web_search"}}]
    )
    return completion.choices[0]

def main():
    messages = [{"role": "system", "content": "你是 Kimi。"}]
    messages.append({"role": "user", "content": "请搜索 Moonshot AI Context Caching 技术，并告诉我它是什么。"})

    finish_reason = None
    while finish_reason is None or finish_reason == "tool_calls":
        choice = chat(messages)
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls":
            messages.append(choice.message)
            for tool_call in choice.message.tool_calls:
                tool_call_name = tool_call.function.name
                tool_call_arguments = json.loads(tool_call.function.arguments)
                if tool_call_name == "$web_search":
                    tool_result = search_impl(tool_call_arguments)
                else:
                    tool_result = f"Error: unable to find tool by name '{tool_call_name}'"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call_name,
                    "content": json.dumps(tool_result),
                })
    print(choice.message.content)

if __name__ == '__main__':
    main()
```

#### 关于 Tokens 消耗

`$web_search` 函数执行结果是一个包含搜索结果的结构化数据，这部分数据也会被计入 Tokens 消耗。搜索结果占用的 Tokens 数量可以在返回的 `tool_call.function.arguments` 中获取。

当触发了联网搜索 `$web_search` 工具调用时，总计费 Tokens 为：

```
total_tokens = prompt_tokens + search_tokens + completions_tokens
```

#### 关于模型选择

由于启用了联网搜索功能后 Tokens 数量会发生较大变化，建议使用 `kimi-k2.6` 模型以适应 Tokens 变化的情况。

#### 关于其他 tools

`$web_search` tools 可以与其他普通 tools 混合使用，可以自由组合 `type=builtin_function` 和 `type=function` 的 tools。

#### 思考模式兼容性

官方内置的 `builtin_function` 的联网搜索 `$web_search` 工具暂时与 Kimi K2.6/Kimi K2.5 思考模式不兼容，可以选择先关闭思考模式后使用联网搜索工具 `$web_search`。

### 7.6 官方工具列表与 Formula 概念

#### Kimi 官方工具列表

Kimi 开放平台特别推出官方工具，目前限时免费集成到应用程序中：

| 工具名称 | 工具描述 |
|---------|---------|
| `convert` | 单位转换工具，支持长度、质量、体积、温度、面积、时间、能量、压力、速度和货币的单位换算 |
| `web-search` | 实时信息及互联网检索工具 |
| `rethink` | 智能整理想法工具 |
| `random-choice` | 随机选择工具 |
| `mew` | 随机产生猫的叫声和祝福的工具 |
| `memory` | 记忆存储和检索系统工具，支持对话历史、用户偏好等数据的持久化 |
| `excel` | Excel 和 CSV 文件的分析工具 |
| `date` | 日期时间处理工具 |
| `base64` | Base64 编码与解码工具 |
| `fetch` | URL 内容提取 Markdown 格式化工具 |
| `quickjs` | 使用 Quick JS 引擎安全执行 JavaScript 代码的工具 |
| `code_runner` | Python 代码执行工具 |

对应的 Formula URI：

- `moonshot/convert:latest`
- `moonshot/web-search:latest`
- `moonshot/rethink:latest`
- `moonshot/random-choice:latest`
- `moonshot/mew:latest`
- `moonshot/memory:latest`
- `moonshot/excel:latest`
- `moonshot/date:latest`
- `moonshot/base64:latest`
- `moonshot/fetch:latest`
- `moonshot/quickjs:latest`
- `moonshot/code_runner:latest`

#### Formula 概念

理解 Kimi 官方工具之前，需要学习 **Formula** 概念。Formula 是一个轻量脚本引擎集合。它可以将 Python 脚本转化为"可被 AI 一键触发的瞬态算力"，让开发者只需专注于代码编写，其余的启动、调度、隔离、计费、回收等工作都由平台负责。

Formula 通过语义化的 URI（如 `moonshot/web-search:latest`）来调用，每个 formula 包含声明（告诉 AI 能干什么）和实现（Python 代码），平台会自动处理所有底层细节。

#### 调用官方工具的方法

一个典型的用法是如果需要调用 web search，可以发一个 HTTP request：

```bash
export FORMULA_URI="moonshot/web-search:latest"
export MOONSHOT_BASE_URL="https://api.moonshot.cn/v1"

curl -X POST ${MOONSHOT_BASE_URL}/formulas/${FORMULA_URI}/fibers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MOONSHOT_API_KEY" \
  -d '{
    "name": "web_search",
    "arguments": "{\"query\": \"月之暗面最近有什么消息\"}"
  }'
```

#### 和 Chat Completions 的交互说明

**tools 字段怎么设置？**

给定 formula uri（如 `moonshot/web-search:latest`），可以获取工具定义：

```bash
curl ${MOONSHOT_BASE_URL}/formulas/${FORMULA_URI}/tools \
  -H "Authorization: Bearer $MOONSHOT_API_KEY"
```

返回的 `tools` 字段是一个 array of dict，可以直接追加到请求的 tools 列表中。

**模型请求返回的处理**

如果 chat completion 返回 `finish_reason=tool_calls`，说明模型触发了工具调用。需要通过 `choices[0].message.tool_calls[0].function.name` 发现需要调用的工具，然后向 `${MOONSHOT_BASE_URL}/formulas/${FORMULA_URI}/fibers` 发出请求。

**Fiber 请求返回的处理**

Fiber 是一次具体执行的"进程快照"，含日志、Tracing、资源用量。

POST 的结果 `status` 可能是 `succeeded` 或者各种类型的错误。当 `succeeded` 后，结果可能在 `context.output` 或 `context.encrypted_output` 中。

#### 注意要点

- 模型可能会返回超过一个 tool_calls，因此**必须对所有 tool_calls 都给出返回**模型才会继续
- assistant 如果带 tool_calls，接下来必定是和 tool_calls 数量一致的几个 `role=tool` 的 message
- `tool_call_id` 要求和前面的 `tool_calls.id` 一一对齐
- 多个 tool_calls 顺序不敏感

---

## 8. 文件问答

### 8.1 文件上传与抽取

Kimi API 提供了上传文件、并基于文件进行问答的能力。基本流程如下：

1. 通过文件上传接口 `/v1/files` 或 SDK 中的 `files.create` API 将文件上传至 Kimi 服务器
2. 通过文件抽取接口 `/v1/files/{file_id}` 或 SDK 中的 `files.content` API 获取文件内容
3. 将文件抽取后的内容（而不是文件 `id`），以系统提示词 system prompt 的形式放置在 messages 列表中
4. 开始对文件内容的提问

> **再次注意，请将文件内容放置在 prompt 中，而不是文件的 `file_id`。**

**Python 示例：**

```python
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

file_object = client.files.create(
    file=Path("moonshot.pdf"),
    purpose="file-extract"
)

file_content = client.files.content(file_id=file_object.id).text

messages = [
    {"role": "system", "content": "你是 Kimi。"},
    {"role": "system", "content": file_content},
    {"role": "user", "content": "请简单介绍 moonshot.pdf 的具体内容"},
]

completion = client.chat.completions.create(
    model="kimi-k2.6",
    messages=messages
)
print(completion.choices[0].message)
```

### 8.2 单文件问答

单文件问答的基本步骤已经在 8.1 中展示。核心要点是：

- 使用 `purpose="file-extract"` 上传文件
- 通过 `client.files.content(file_id=...).text` 获取文件内容
- 将文件内容作为 system prompt 放入 messages 中

### 8.3 多文件问答

如果想针对多个文件内容进行提问，将每个文件单独放置在一个系统提示词 system prompt 中即可：

```python
from typing import *
import os
import json
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

def upload_files(files: List[str]) -> List[Dict[str, Any]]:
    messages = []
    for file in files:
        file_object = client.files.create(file=Path(file), purpose="file-extract")
        file_content = client.files.content(file_id=file_object.id).text
        messages.append({"role": "system", "content": file_content})
    return messages

def main():
    file_messages = upload_files(files=["upload_files.py"])

    messages = [
        *file_messages,
        {"role": "system", "content": "你是 Kimi。"},
        {"role": "user", "content": "总结一下这些文件的内容。"},
    ]

    completion = client.chat.completions.create(
        model="kimi-k2.6",
        messages=messages,
    )
    print(completion.choices[0].message.content)

if __name__ == '__main__':
    main()
```

### 8.4 文件管理最佳实践

通常而言，文件上传和文件抽取功能旨在将不同格式的文件提取成模型易于理解的格式。在完成文件上传和文件抽取步骤后，抽取后的内容可以在本地进行存储，在下一次基于文件的问答请求中，不必再次进行上传和抽取动作。

由于单用户的文件上传数量有限制（**每个用户最多上传 1000 个文件**），因此建议在文件抽取过程进行完毕后，定期清理已上传的文件：

```python
from openai import OpenAI

client = OpenAI(api_key="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1")

file_list = client.files.list()
for file in file_list.data:
    client.files.delete(file_id=file.id)
```

---


## 9. 产品定价

### 9.1 计费基本概念

#### 计费单元

**Token**：代表常见的字符序列，每个汉字使用的 Token 数目可能是不同的。例如，单个汉字"夔"可能会被分解为若干 Token 的组合，而像"中国"这样短且常见的短语则可能会使用单个 Token。大致来说，对于一段通常的中文文本，1 个 Token 大约相当于 1.5-2 个汉字。具体每次调用实际产生的 Tokens 数量可以通过调用计算 Token API 来获得。

#### 计费逻辑

Chat Completion 接口收费：对 Input 和 Output 均实行按量计费。如果您上传并抽取文档内容，并将抽取的文档内容作为 Input 传输给模型，那么文档内容也将按量计费。文件相关接口（文件内容抽取/文件存储）接口**限时免费**。

### 9.2 Kimi K2.6 定价

| 模型 | 计费单位 | 输入价格（缓存命中） | 输入价格（缓存未命中） | 输出价格 | 上下文窗口 |
|------|---------|-------------------|---------------------|---------|----------|
| kimi-k2.6 | 1M tokens | ¥1.10 | ¥6.50 | ¥27.00 | 262,144 tokens |

此处 1M = 1,000,000，表格中的价格代表每消耗 1M tokens 的价格。

**模型说明**：

- **Kimi K2.6** 是 Kimi 最新最智能的模型，具备更强更稳的长程代码编写能力，指令遵循和自我纠错能力显著提升
- 同时支持文本、图片与视频输入，思考与非思考模式，对话与 Agent 任务
- 模型上下文长度 256k，支持长思考擅长深度推理
- 支持自动上下文缓存功能

#### 其他模型定价参考

| 模型 | 计费单位 | 输入价格（缓存命中） | 输入价格（缓存未命中） | 输出价格 | 上下文窗口 |
|------|---------|-------------------|---------------------|---------|----------|
| kimi-k2.7-code | 1M tokens | ¥1.30 | ¥6.50 | ¥27.00 | 262,144 tokens |
| kimi-k2.7-code-highspeed | 1M tokens | ¥2.60 | ¥13.00 | ¥54.00 | 262,144 tokens |
| kimi-k2.5 | 1M tokens | ¥0.70 | ¥4.00 | ¥21.00 | 262,144 tokens |

### 9.3 批量推理定价

Batch API 即批量推理 API，批量推理 API 费用为标准模型价格的 **60%**，适合大规模、低实时性要求的任务场景。

| 模型 | 计费单位 | 输入价格（缓存命中） | 输入价格（缓存未命中） | 输出价格 | 上下文窗口 |
|------|---------|-------------------|---------------------|---------|----------|
| kimi-k2.7-code（Batch） | 1M tokens | ¥0.78 | ¥3.90 | ¥16.20 | 262,144 tokens |
| kimi-k2.6（Batch） | 1M tokens | ¥0.66 | ¥3.90 | ¥16.20 | 262,144 tokens |
| kimi-k2.5（Batch） | 1M tokens | ¥0.42 | ¥2.40 | ¥12.60 | 262,144 tokens |

**说明**：

- Batch API 支持 `kimi-k2.7-code`、`kimi-k2.6` 和 `kimi-k2.5` 模型
- Batch API 不受实时并发限制，适合大批量任务
- 任务需在指定的 `completion_window` 内完成，超时将变为 `expired` 状态

### 9.4 联网搜索定价

| 工具名称 | 计费单位 | 价格 | 说明 |
|---------|---------|------|------|
| 联网搜索 | 1 次 | ￥0.03 | 触发 `$web_search` 工具调用，计费一次 |

**联网搜索计费逻辑**：

当你在 `tools` 中加入 `$web_search` 工具，并获得了一个 `finish_reason = tool_calls` 且 `tool_call.function.name = $web_search` 的响应时，收取联网搜索调用费用 0.03 元；当响应 `finish_reason = stop` 时，不收取调用费用。

此外，使用 `$web_search` 时，依然会按照不同模型收取 `/chat/completions` 接口产生的 Tokens 费用。值得注意的是，当触发了联网搜索，搜索结果也会被计入 Tokens 中。

> **注**：如果你在触发了联网搜索 `$web_search` 时，不继续完成 `tool_calls`，而是就此停止，那么只会收取 ¥0.03 元的工具调用费用，联网搜索内容占用的 Tokens 将不会计费。

### 9.5 充值与限速

为了整体资源分配的公平性，同时防止恶意攻击，目前基于账户的累计充值金额进行速率限制：

| 用户等级 | 累计充值金额 | 并发 | RPM | TPM | TPD |
|---------|------------|------|-----|-----|-----|
| Tier0 | ¥ 0 | 1 | 3 | 500,000 | 1,500,000 |
| Tier1 | ¥ 50 | 50 | 200 | 2,000,000 | Unlimited |
| Tier2 | ¥ 100 | 100 | 500 | 3,000,000 | Unlimited |
| Tier3 | ¥ 500 | 200 | 5,000 | 3,000,000 | Unlimited |
| Tier4 | ¥ 5,000 | 400 | 5,000 | 4,000,000 | Unlimited |
| Tier5 | ¥ 20,000 | 1,000 | 10,000 | 5,000,000 | Unlimited |

#### 限速概念解释

- **并发**：同一时间内最多处理的来自您的请求数
- **RPM**：requests per minute，指一分钟内最多发起的请求数
- **TPM**：tokens per minute，指一分钟内最多交互的 token 数
- **TPD**：tokens per day，指一天内最多交互的 token 数

#### 为什么要做限速？

1. **防止滥用**：有助于防止滥用或误用 API
2. **公平访问**：确保每个人都能公平地访问 API
3. **管理负载**：帮助管理集群总负载，为所有用户维护平稳且一致的体验

#### 特别说明

- 将全力保障用户的正常使用，但当集群负载达到容量上限时，可能会采取临时的限流措施
- **代金券不计入累计充值总额**

---

## 10. 上下文缓存

### 10.1 自动缓存机制

Kimi K2.6 模型支持**自动上下文缓存**功能。这意味着模型会自动对重复出现的上下文内容进行缓存，当后续请求中包含相同或相似的上下文时，可以直接利用缓存结果，从而减少 Tokens 消耗和响应时间。

缓存机制的工作原理：

1. 当请求中的部分上下文内容与之前请求高度重合时，系统会自动识别并缓存这部分内容
2. 后续请求中相同的上下文部分将被标记为"缓存命中"
3. 缓存命中的部分按照更低的价格计费（详见第 9 章定价表中的"输入价格（缓存命中）"列）

### 10.2 与 RAG 方案的比较

| 特性 | 上下文缓存 | RAG（检索增强生成） |
|------|-----------|-------------------|
| 实现复杂度 | 无需额外开发，系统自动处理 | 需要构建向量数据库、检索系统等 |
| 适用场景 | 对话历史、重复性高的上下文 | 大规模知识库、文档检索 |
| 精度 | 完全匹配缓存内容 | 基于相似度检索，可能有遗漏 |
| 成本 | 缓存命中时成本更低 | 需要额外的检索成本 |

### 10.3 计费说明与最佳实践

- 缓存命中时，输入 Tokens 按照"缓存命中"价格计费，显著低于"缓存未命中"价格
- 缓存机制是自动的，无需在请求中额外配置
- 为了最大化缓存命中率，建议：
  - 保持 system prompt 的稳定性
  - 在多轮对话中避免频繁修改历史消息
  - 对于重复性高的任务，尽量复用相同的上下文结构

---

## 11. 错误处理与常见问题

### 11.1 常见错误类型

| HTTP 状态码 | 错误类型 | 说明 | 解决方案 |
|------------|---------|------|---------|
| 400 | 请求错误 | 请求参数不正确或缺失 | 检查请求参数是否符合 API 文档要求 |
| 401 | 认证失败 | API Key 无效或已过期 | 检查 API Key 是否正确，是否需要重新生成 |
| 429 | 速率限制 | 请求频率超过限制 | 降低请求频率，或联系销售提升速率限制 |
| 500 | 服务端错误 | 服务器内部错误 | 稍后重试，如果持续出现请联系技术支持 |

#### invalid_request_error

Schema 格式本身不合法时，API 会返回 `400`，错误类型为 `invalid_request_error`：

```json
{
    "error": {
        "message": "Invalid request: the `response_format.json_schema.schema` field in the request is illegal...",
        "type": "invalid_request_error"
    }
}
```

请检查 schema 是否为合法的 JSON Schema 对象。

#### 输出被截断（`finish_reason="length"`）

模型在输出完整内容之前达到了 `max_tokens` 限制。建议：

- 增大 `max_tokens`（例如 4096 或更高）
- 简化 schema 的嵌套层级
- 缩短输入文本长度
- 使用 Partial Mode 续接被截断的输出（详见第 4.4 节）

#### Input token length too long

当输入 Tokens 数量超过了模型支持的上下文窗口大小时触发。建议：

- 使用更大上下文窗口的模型（如 `kimi-k2.6`）
- 精简 messages 列表，移除不必要的历史消息
- 减少上传文件的内容量

#### tool_call_id not found

如果你遇到 `tool_call_id not found` 错误，可能是由于你未将 API 返回的 `role=assistant` 消息添加到 messages 列表中。正确的消息序列应该包含 assistant message（含 tool_calls）后紧跟对应的 tool messages。

### 11.2 自动断线重连

在使用流式输出时，可能会因为网络问题导致连接中断。建议实现以下重连机制：

1. 捕获网络异常（如 `ReadTimeout`、`ConnectionError` 等）
2. 等待一段时间后重试（指数退避策略）
3. 如果使用了流式输出，可以记录最后成功接收的 token 位置，在重连后从该位置继续

### 11.3 注意事项汇总

#### 一般注意事项

1. **API Key 安全**：不要在客户端代码、公开仓库或日志中暴露 API Key
2. **temperature 不可修改**：K2.6/K2.5 系列模型的 temperature 不可修改，使用默认值即可
3. **max_tokens 默认值**：默认值为 32k（32768），一般无需手动设置
4. **流式输出推荐**：思考模型的输出内容包含了 `reasoning_content`，相比普通模型其输出内容更多，启用流式输出能获得更好的用户体验

#### 思考模式注意事项

1. **保留 reasoning_content**：使用工具时，单轮任务内应保留上下文中所有的 `reasoning_content`
2. **max_tokens 建议值**：设置 `max_tokens >= 16000` 以避免无法输出完整的推理内容
3. **联网搜索不兼容**：`$web_search` 与思考模式暂时不兼容，使用联网搜索时需要先关闭思考

#### 视觉模型注意事项

1. **分辨率建议**：图片不超过 4K，视频不超过 1080p
2. **大视频使用文件上传**：非常大的视频必须使用上传文件的方式
3. **URL 图片不支持**：目前仅支持 base64 编码的图片内容
4. **Content 格式**：使用 Vision 模型时，`message.content` 必须是数组格式，不要序列化为字符串

#### 工具调用注意事项

1. **消息布局**：确保每个 `tool_call` 都有对应的 `role=tool` 消息，且 `tool_call_id` 正确对应
2. **并行调用**：`tool_calls` 支持并行调用，可同时返回多个工具调用
3. **Tokens 计算**：`tools` 参数中的内容也会被计算在总 Tokens 中

#### 文件问答注意事项

1. **放置文件内容而非 ID**：将文件抽取后的内容放置在 prompt 中，而不是文件的 `file_id`
2. **文件数量限制**：每个用户最多上传 1000 个文件
3. **定期清理文件**：建议在文件抽取完成后定期清理已上传的文件

---

*本文档由 Kimi API 开放平台多个文档整合而成，原始来源：https://platform.kimi.com*

**相关链接：**
- [Kimi 开放平台](https://platform.kimi.com)
- [GitHub](https://github.com/MoonshotAI)
- [API 文档中心](https://platform.kimi.com/docs)
