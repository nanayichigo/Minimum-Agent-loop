# OpenAI Responses API —— `input` 中 `content` 可用 type 说明

> 适用：`openai` Python SDK（本文基于 **2.41.0** 源码整理，`openai/types/responses/`）。
> 调用入口：`client.responses.create(model=..., input=...)`。

---

## 一、`input` 参数总览

`input` 参数的类型是 `Union[str, ResponseInputParam]`，即两种写法：

| 写法 | 形式 | 说明 |
|---|---|---|
| 纯字符串 | `input="你好"` | 最简单，整段作为一条 user 文本消息 |
| 消息数组 | `input=[{...}, {...}]` | 结构化输入，每条为一个 message item |

消息数组中的每条 message item 结构（`EasyInputMessageParam`）：

```json
{
  "role": "user",          // user / assistant / system / developer
  "content": "..."         // 字符串，或 content 块列表（见下表）
}
```

- `role` 取值：`user`、`assistant`、`system`、`developer`。其中 `developer` / `system` 指令优先级高于 `user`；`assistant` 用于回放模型历史输出。
- `content` 有两种：**字符串**，或 **content 块列表**（即本文要讲的 type）。
- 可选字段 `phase`（仅 `assistant` 消息）：`"commentary"`（中间推理）或 `"final_answer"`（最终回答），用于 gpt-5.3-codex 等模型。

```python
# content 为字符串
input=[{"role": "user", "content": "你好"}]

# content 为块列表（多模态）
input=[{"role": "user", "content": [
    {"type": "input_text", "text": "请分析这张图"},
    {"type": "input_image", "image_url": "..."},
]}]
```

---

## 二、`content` 可用 type 总表

| type | 用途 | 必填字段 | 可选字段 | 说明 |
|---|---|---|---|---|
| `input_text` | 纯文本 | `text` | — | 最基础的文本输入 |
| `input_image` | 图片（视觉理解） | `image_url` 或 `file_id`（二选一） | `detail` | 支持 PNG / JPEG / WEBP |
| `input_file` | 文件（如 PDF） | `file_data` / `file_id` / `file_url`（至少一个） | `filename`、`detail` | 需模型同时支持文本+图像输入 |
| `input_audio` | 音频（语音理解） | `input_audio.data`、`input_audio.format` | — | ⚠️ 见下方说明 |

> **关于 `input_audio` 的特别说明**：在 SDK 2.41.0 中，`input_audio` 类型已定义（`ResponseInputAudioParam`）并在 `openai/types/responses/__init__.py` 中导出，但**尚未纳入 message `content` 的类型联合体**（`ResponseInputContentParam` = text/image/file 三种）。因此：
> - 若直接按 `{"type": "input_audio", "input_audio": {...}}` 结构以字典形式传入，通常仍能被 API 接受；
> - 但若依赖 IDE 类型提示 / 静态检查，可能不被识别，属正常现象。
> - 其结构与其余三种不同，是**嵌套结构**（见 3.4）。

---

## 三、各 type 字段详解

### 3.1 `input_text` —— 文本

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | str | ✅ | 固定为 `"input_text"` |
| `text` | str | ✅ | 要发送给模型的文本内容 |

```python
{"type": "input_text", "text": "What is in this image?"}
```

---

### 3.2 `input_image` —— 图片

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | str | ✅ | 固定为 `"input_image"` |
| `image_url` | str | ⚠️ 与 `file_id` 二选一 | 图片 URL，或 base64 data URL（`data:image/jpeg;base64,...`） |
| `file_id` | str | ⚠️ 与 `image_url` 二选一 | 已上传文件的 ID（Files API） |
| `detail` | str | ❌ | 细节等级：`low` / `high` / `auto` / `original`，默认 `auto` |

```python
# URL 方式
{"type": "input_image", "image_url": "https://example.com/cat.jpg"}

# base64 data URL 方式（附带 detail）
{"type": "input_image",
 "image_url": "data:image/jpeg;base64,<base64串>",
 "detail": "auto"}

# file_id 方式
{"type": "input_image", "file_id": "file-xxx"}
```

> `detail` 说明：`low` 低分辨率（省钱/省 token），`high` 高分辨率（细节更准），`auto` 由模型自行判断，`original` 使用原图分辨率。

---

### 3.3 `input_file` —— 文件

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | str | ✅ | 固定为 `"input_file"` |
| `file_data` | str | ⚠️ 三选一 | 文件内容，base64 data URL 形式（如 `data:application/pdf;base64,...`） |
| `file_id` | str | ⚠️ 三选一 | 已上传文件的 ID（Files API） |
| `file_url` | str | ⚠️ 三选一 | 文件的可访问 URL |
| `filename` | str | ❌ | 文件名（使用 `file_data` 内联时建议填写） |
| `detail` | str | ❌ | 渲染质量：`low` / `high`，默认 `low` |

```python
# 内联 base64
{"type": "input_file",
 "file_data": "data:application/pdf;base64,<base64串>",
 "filename": "report.pdf"}

# 已上传文件
{"type": "input_file", "file_id": "file-xxx"}

# 文件 URL
{"type": "input_file", "file_url": "https://example.com/report.pdf"}
```

> **注意**：`file_data`、`file_id`、`file_url` 三者**至少提供一个**，否则 API 会报错。用 `file_data` 时建议同时给 `filename`，模型才能识别文件类型。

---

### 3.4 `input_audio` —— 音频

> ⚠️ 与上面三种不同，`input_audio` 是**嵌套结构**：外层 `type` + 内层 `input_audio` 对象。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | str | ✅ | 固定为 `"input_audio"` |
| `input_audio` | object | ✅ | 嵌套对象，见下 |
| `input_audio.data` | str | ✅ | **base64 编码**的音频数据（注意：不是 data URL，是纯 base64 串） |
| `input_audio.format` | str | ✅ | 音频格式：`mp3` 或 `wav` |

```python
{"type": "input_audio",
 "input_audio": {
     "data": "<纯base64串>",
     "format": "wav"      # 或 "mp3"
 }}
```

> **注意**：`data` 是**纯 base64 字符串**，与 `input_image`/`input_file` 的 data URL 前缀（`data:...;base64,`）不同。

---

## 四、完整使用示例

### 4.1 纯文本

```python
from openai import OpenAI

client = OpenAI()

resp = client.responses.create(
    model="gpt-4o",
    input="你好，介绍一下你自己",
)
```

### 4.2 文本 + 图片（多模态）

```python
resp = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "这张图里有什么？"},
                {"type": "input_image",
                 "image_url": "https://example.com/cat.jpg",
                 "detail": "auto"},
            ],
        }
    ],
)
```

### 4.3 文本 + 文件（PDF）

```python
import base64

with open("report.pdf", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "总结这份 PDF 的核心内容"},
                {"type": "input_file",
                 "file_data": f"data:application/pdf;base64,{b64}",
                 "filename": "report.pdf"},
            ],
        }
    ],
)
```

### 4.4 文本 + 音频

```python
import base64

with open("speech.wav", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

resp = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "这段录音说了什么？"},
                {"type": "input_audio",
                 "input_audio": {"data": audio_b64, "format": "wav"}},
            ],
        }
    ],
)
```

### 4.5 多轮对话（回放 assistant 历史）

```python
resp = client.responses.create(
    model="gpt-4o",
    input=[
        {"role": "user", "content": "1+1 等于几？"},
        {"role": "assistant", "content": "等于 2。"},
        {"role": "user", "content": "那 2+2 呢？"},
    ],
)
```

---

## 五、注意事项

1. **`input` 顶层是字符串时**，等价于单条 `user` 文本消息，不可附带图片/文件/音频。
2. **图片与文件的来源互斥规则**：
   - `input_image`：`image_url` 与 `file_id` 二选一；
   - `input_file`：`file_data` / `file_id` / `file_url` 三选一（至少一个）。
3. **base64 编码格式差异**：
   - `input_image.image_url` 与 `input_file.file_data` 需要带 data URL 前缀（`data:...;base64,`）；
   - `input_audio.input_audio.data` 是**纯 base64 串**，不带前缀。
4. **文件/图片支持依赖模型能力**：并非所有模型都支持视觉或文件输入，PDF 通常需要同时支持文本+图像输入的模型（如 `gpt-4o` 系列）。
5. **`input_audio` 为较新的输入类型**：SDK 2.41.0 已定义其结构但尚未纳入 `content` 类型联合体，类型提示可能不识别，属正常现象；以字典形式传入即可。
6. **`assistant` 消息的 `phase` 字段**（`commentary` / `final_answer`）在 gpt-5.3-codex 等模型的多轮追问中应原样保留，否则可能影响效果。

---

## 参考来源

- 本机 SDK 源码：`openai/types/responses/response_input_*_param.py`（openai==2.41.0）
- [OpenAI Responses API 官方参考](https://platform.openai.com/docs/api-reference/responses/create)
- [OpenAI Vision 指南](https://platform.openai.com/docs/guides/vision)
