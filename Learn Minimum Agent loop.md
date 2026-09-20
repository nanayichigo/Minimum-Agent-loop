# 最小 Agent 循环 —— 具体怎么学

> 对应《AI-Agent开发学习路线-2026.md》**阶段 1**。目标就一个：**不用任何框架，用 OpenAI 最新的 Responses API 手写一个「多工具助手」**，让你亲眼看到 Agent 的「思考 → 行动 → 观察」是怎么循环起来的。
>
> 全文遵循一个原则：**每一步都能跑、每一步都有「验证标准」**。别光看，跟着敲。

> ⚠️ **先说一个重要的前提**：本文用的是 OpenAI **Responses API**（2025 年起 OpenAI 推行的新接口，取代旧的 Chat Completions）。它目前**基本只有 OpenAI 官方支持**——DeepSeek、通义、智谱、Kimi 等国内厂商的"OpenAI 兼容"接口，**绝大多数仍只支持旧的 Chat Completions**。所以：
> - 如果你用 **OpenAI 官方**：直接照本文跑。
> - 如果你用**国内模型**：先查该家是否已支持 Responses API；不支持的话，改用旧的 `client.chat.completions.create()` 写法（结构一样，只是消息格式是 `messages` + `role: "tool"`）。
>
> 别被这个绕晕——**你学的是「Agent 循环」这个思想，接口只是载体**。思想学会了，换任何接口都只是改几行格式。

---

## 0. 先想清楚：你要学的到底是什么

「最小 Agent 循环」拆开就是 4 块，**每一块都能独立验证**：

| 块 | 一句话 | 你会写出来的东西 |
|---|---|---|
| ① 调用 LLM | 发消息、收回复 | 一个 `client.responses.create(...)` |
| ② 工具定义 | 告诉模型「有哪些工具、参数长啥样」 | 一段 JSON Schema |
| ③ 工具执行 | 模型不会真的执行，**你来执行** | 几个普通 Python 函数 |
| ④ 循环 | 把①②③包进 while，直到模型说「答完了」 | 一个 `for/while` + 输入历史数组 |

学完的标准（路线里的原话）：**能连续调用多个工具、把上一步结果喂给下一步，直到给出最终答案**。

---

## 1. 环境准备

```bash
pip install openai requests
```

```python
from openai import OpenAI

client = OpenAI(api_key="你的 key")   # OpenAI 官方，无需 base_url
```

**验证标准**：下面这段能打印出模型的回复。注意 Responses API 用 `input` 传消息、用 `output_text` 取回答。

```python
resp = client.responses.create(
    model="gpt-4o-mini",   # 换成你账号能用的模型名
    input="你好",
)
print(resp.output_text)
```

> ⚠️ 一个容易懵的点：`model=` 这里填的是**模型名**（如 `gpt-4o-mini`、`gpt-4.1-mini`），去 OpenAI 文档查你账号可用哪个。

---

## 2. 必须先懂的 3 个概念（10 分钟，读到这里就行）

### 2.1 `input` 是「对话历史列表」，里面有两种东西

LLM 每次对话其实是把**整个历史**重发一遍。Responses API 里这个历史叫 `input`，可以是一个字符串，也可以是一个列表。列表里的**条目（item）分两类**：

| 谁说的 | 用什么表示 |
|---|---|
| 你（开发者）的规则 | `instructions="..."` 参数（相当于旧版的 system prompt） |
| 用户的任务 | `{"role": "user", "content": "..."}` |
| 模型上一步的输出（含它想调哪个工具） | 直接把 `resp.output` 追加回 `input` |
| 工具的执行结果 | `{"type": "function_call_output", "call_id": "...", "output": "..."}` |

**关键认知**：Agent 循环的本质，就是**不断往 `input` 里追加「模型输出」和「工具结果」**。

### 2.2 Function Calling：模型「要求」调工具，但**不自己调**

当你把工具清单发给模型后，模型不会真的执行你的函数。它会在 `resp.output` 里返回一个 **`function_call` 对象**，内容是：**「我想调 `get_weather`，参数是 `{"city": "北京"}`」**。真正执行函数的是你，然后把结果用 `function_call_output` 回填给它。

```python
resp = client.responses.create(model="...", input="...", tools=tools)

for item in resp.output:
    if item.type == "function_call":     # 这就是模型发出的「调工具请求」
        print(item.name, item.arguments) # name="get_weather"，arguments='{"city":"北京"}'
```

### 2.3 JSON Schema：用结构化文字描述一个工具

模型怎么知道 `get_weather` 要什么参数？靠你写的一段 JSON。**注意 Responses API 的工具格式是"平铺"的**（`name` 直接在顶层，不像旧版要套一层 `function`）：

```json
{
  "type": "function",
  "name": "get_weather",
  "description": "查询某城市的当前天气",
  "parameters": {
    "type": "object",
    "properties": { "city": { "type": "string", "description": "城市名" } },
    "required": ["city"]
  }
}
```

只需要看懂 `type` / `properties` / `required` 三个词。**这段描述写得清不清楚，直接决定模型调得对不对**——这是 Agent 开发的第一个「手艺活」。

---

## 3. 渐进式手写（核心，分 4 步）

> 关键方法：**不要一口气写出完整循环**。按下面 4 步走，每步都只比上一步多一点点，跑通了再进下一步。

### 步骤 1：只做「一次工具往返」（先不写循环）

目标：理解 **Function Calling 的最小闭环**——发请求 → 模型要调工具 → 你手动执行 → 回填结果 → 模型给最终答案。

```python
import json
import requests   # 发 HTTP 请求用
from openai import OpenAI

client = OpenAI(api_key="...")

# —— 真实天气查询：用 open-meteo 免费接口，无需注册、无需 API key ——
WEATHER_TEXT = {
    0: "晴", 1: "基本晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "阵雨", 82: "强阵雨",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "雷暴伴冰雹",
}

def get_weather(city: str) -> str:
    # 第 1 步：城市名 -> 经纬度（免费地理编码接口）
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "zh"},
        timeout=10,
    ).json()
    if not geo.get("results"):
        return f"查不到城市「{city}」，换个写法试试"
    loc = geo["results"][0]

    # 第 2 步：经纬度 -> 当前天气
    w = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": loc["latitude"], "longitude": loc["longitude"],
                "current": "temperature_2m,weather_code,wind_speed_10m"},
        timeout=10,
    ).json()
    cur = w["current"]
    desc = WEATHER_TEXT.get(cur["weather_code"], f"天气码 {cur['weather_code']}")
    return f"{city} 当前{desc}，{cur['temperature_2m']}°C，风速 {cur['wind_speed_10m']} km/h"

tools = [{ "type": "function", "name": "get_weather", ... 上面的 JSON Schema ... }]

# 第一次请求：模型会返回 function_call
resp = client.responses.create(
    model="gpt-4o-mini",
    instructions="你是一个助手，需要时调用工具获取信息，最后用中文回答。",
    input="北京今天天气怎么样？",
    tools=tools,
)
tool_call = next(o for o in resp.output if o.type == "function_call")
print("模型想调：", tool_call.name, tool_call.arguments)

# 手动执行 + 回填
args = json.loads(tool_call.arguments)          # arguments 是字符串！
result = get_weather(**args)

# 第二次请求：把「用户原话 + 模型请求 + 工具结果」一起发回
resp2 = client.responses.create(
    model="gpt-4o-mini",
    instructions="你是一个助手，需要时调用工具获取信息，最后用中文回答。",
    input=[
        {"role": "user", "content": "北京今天天气怎么样？"},
        tool_call,                               # 模型上一步的 function_call 也要放回上下文
        {"type": "function_call_output", "call_id": tool_call.call_id, "output": result},
    ],
    tools=tools,
)
print("最终答案：", resp2.output_text)
```

**验证标准**：控制台能打出「模型想调 get_weather …」+ 一句最终答案。跑通后，**手动删掉 `input` 里的 `tool_call` 那一行**再跑，观察模型会报错还是答错——这会让你直观理解「为什么必须把模型上一步的输出也放回上下文」。

> 提示：第二次请求也可以用 `previous_response_id=resp.id` 来「接着上一步」，只传工具结果即可，不用手动拼全历史。但这里**故意手动拼**，是为了让你看清底层的机制。

### 步骤 2：把步骤 1 包进 `for` 循环

现在把「手动」变成「自动」：模型只要还在要求调工具，就一直循环；一旦它不再返回 `function_call`（直接给答案），就退出。

```python
def run_agent(task: str, max_steps: int = 5) -> str:
    instructions = "你是一个助手，需要时调用工具，最后用中文回答。"
    input_items = [{"role": "user", "content": task}]

    for _ in range(max_steps):
        resp = client.responses.create(
            model="gpt-4o-mini",
            instructions=instructions,
            input=input_items,
            tools=tools,
        )
        input_items += resp.output                    # 把本轮模型输出追加进历史

        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:                                 # 没有工具调用 = 模型直接给了最终答案
            return resp.output_text

        for tc in calls:                              # 一次可能请求多个工具
            args = json.loads(tc.arguments)
            result = get_weather(**args)
            input_items.append({
                "type": "function_call_output",
                "call_id": tc.call_id,
                "output": result,
            })

    return "达到最大步数仍未得到答案"
```

**验证标准**：`run_agent("北京天气如何？")` 一句话搞定。这一步你已经**写出了一个 Agent**——虽然只有 1 个工具、30 行代码。

### 步骤 3：加多个工具，验证「连续调用、结果串联」

把工具从 1 个变成 3 个（路线建议的经典组合：查天气 / 汇率 / 当前时间），用一个字典把「工具名 → 真实函数」对应起来：

```python
def get_weather(city): ...   # 用步骤 1 的真实实现
def get_exchange_rate(a, b): return "1 USD = 7.2 CNY"
def get_current_time(): return "2026-09-18 15:00"

TOOL_FUNCS = {"get_weather": get_weather,
              "get_exchange_rate": get_exchange_rate,
              "get_current_time": get_current_time}
# tools 里放 3 段 JSON Schema；循环体里把 get_weather(**args) 换成 TOOL_FUNCS[name](**args)
```

**验证标准（这是路线原话的关键验收）**：给一个**需要串两步**的任务，比如：
> 「先查北京现在的天气，再告诉我 100 美元能换多少人民币，用当前时间开头。」

模型应该**先调一个工具、拿到结果、再调下一个工具**，最后综合回答。如果它漏调或答错，多半是某段 JSON Schema 的 `description` 写得不够清楚——回去改描述，这正是「Agent 调试」的真实形态。

### 步骤 4：加边界与容错（让它别「裸奔」）

真实的循环会出各种幺蛾子，补三件事：

1. **`max_steps` 上限**（已经有了，改成明确的退出提示）。
2. **`try/except` 包住 `json.loads` 和函数执行**：模型偶尔会给出非法 JSON 或错误参数，捕获后把错误信息当作 `function_call_output` 的 `output` 回填，让模型自己纠正——这就是学习路线阶段 3 要讲的「自纠错」，但你现在就能体会。
3. **打印每一轮日志**：打印「第 N 步：模型要调 X，参数 Y，结果 Z」。你会第一次「看见」Agent 的思考轨迹。

**验证标准**：故意给它一个超出工具能力的任务，观察它「尝试 → 失败 → 承认做不到」，而不是崩溃。

---

## 4. 完整参考实现（~60 行，全注释）

先自己按步骤 1–4 写完，再对照这份。**先写后看**，效果差十倍。

```python
import json
import requests
from openai import OpenAI

client = OpenAI(api_key="你的key")

# —— 工具实现（天气为真实查询；汇率/时间仍是示例假数据）——
WEATHER_TEXT = {0: "晴", 1: "基本晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
                51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
                71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "阵雨", 82: "强阵雨",
                95: "雷暴", 96: "雷暴伴冰雹", 99: "雷暴伴冰雹"}

def get_weather(city):   # 真实查询，完整注释版见步骤 1
    geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                       params={"name": city, "count": 1, "language": "zh"}, timeout=10).json()
    if not geo.get("results"):
        return f"查不到城市「{city}」"
    loc = geo["results"][0]
    w = requests.get("https://api.open-meteo.com/v1/forecast",
                     params={"latitude": loc["latitude"], "longitude": loc["longitude"],
                             "current": "temperature_2m,weather_code,wind_speed_10m"}, timeout=10).json()
    cur = w["current"]
    return f"{city} 当前{WEATHER_TEXT.get(cur['weather_code'], cur['weather_code'])}，{cur['temperature_2m']}°C"

def get_exchange_rate(base, quote):  return f"1 {base} = 7.2 {quote}"
def get_current_time():  return "2026-09-18 15:00"

TOOL_FUNCS = {"get_weather": get_weather,
              "get_exchange_rate": get_exchange_rate,
              "get_current_time": get_current_time}

# —— 工具定义（Responses API 平铺格式，模型看这个）——
def schema(name, desc, props, required):
    return {"type": "function", "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}

TOOLS = [
    schema("get_weather", "查询某城市当前天气", {"city": {"type": "string", "description": "城市名，如 北京"}}, ["city"]),
    schema("get_exchange_rate", "查询两种货币汇率", {"base": {"type": "string"}, "quote": {"type": "string"}}, ["base", "quote"]),
    schema("get_current_time", "获取当前时间", {}, []),
]

def run_agent(task: str, max_steps: int = 6) -> str:
    instructions = "你是助手，需要信息时调用工具，最后用中文自然语言回答。"
    input_items = [{"role": "user", "content": task}]

    for step in range(1, max_steps + 1):
        resp = client.responses.create(model="gpt-4o-mini", instructions=instructions,
                                       input=input_items, tools=TOOLS)
        input_items += resp.output

        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:                              # 没有工具调用 = 循环终点
            return resp.output_text

        for tc in calls:
            print(f"[步骤{step}] 调用 {tc.name}({tc.arguments})")
            try:
                args = json.loads(tc.arguments)    # 参数是 JSON 字符串
                result = TOOL_FUNCS[tc.name](**args)
            except Exception as e:
                result = f"工具调用失败：{e}"        # 错误也回填，让模型自己纠
            input_items.append({"type": "function_call_output",
                                "call_id": tc.call_id, "output": result})

    return "达到最大步数仍未得到答案"

if __name__ == "__main__":
    print(run_agent("先查北京天气，再告诉我 100 美元能换多少人民币，用当前时间开头。"))
```

---

## 5. 对照 smolagents 源码（把手写的映射到真实代码）

你已经 clone 了 smolagents，现在把上面每一行对应到它的源码——**这才是读框架的正确姿势**。注意：你手写的是「JSON Function Calling」风格，对应它的 `ToolCallingAgent`（不是招牌的 `CodeAgent`）。

| 你手写的 | smolagents 里对应的 | 位置 |
|---|---|---|
| `for step in range(max_steps)` 循环 | `while not returned_final_answer and self.step_number <= max_steps` | `src/smolagents/agents.py:545` |
| 入口 `run_agent(task)` | `MultiStepAgent.run()` | `agents.py:436` |
| 一次「思考+要调什么工具」 | `step()`（方法注释就写着 "thinks, acts, and observes"） | `agents.py:782` |
| `if not calls: return resp.output_text` | `returned_final_answer` 标志 + `FinalAnswerStep` | `agents.py:545` |
| `TOOL_FUNCS[name](**args)` | `ToolCallingAgent.execute_tool_call()` | `agents.py:1453` |
| 你手写的 JSON Schema | `@tool` 装饰器**自动从函数签名生成** | `tools.py:1061` + `_function_type_hints_utils.py` |
| `input_items` 累积历史 | `AgentMemory`（`memory.py`）负责记录每一步 | `memory.py` |
| `json.loads(tc.arguments)` | 模型层的参数解析 | `models.py` |

**读法**：只精读第 1、3、4 行指向的那三个方法（`run` / `step` / `execute_tool_call`），你会发现它们**加了一堆「工程细节」（日志、记忆、流式、错误类型）但骨架和你 60 行代码一模一样**——这就是「框架在替你做什么」的答案。

---

## 6. 自测清单（怎么判断你真懂了）

逐条打勾，全勾上才算完成阶段 1：

- [ ] 能不看代码，说出 Function Calling 一次「往返」的完整流程（发→要求调→执行→回填→答）
- [ ] 能说出 `input` 里两种条目（消息 vs `function_call_output`）分别长什么样、由谁产生
- [ ] 能解释「为什么必须把 `resp.output` 追加回 input」（删了会怎样）
- [ ] 自己的 60 行循环，能跑通一个「串两步工具」的任务
- [ ] 工具给错参数时，程序不崩溃、能回填错误让模型重试
- [ ] 能在 smolagents 源码里，指出你写的「循环」「退出判断」「工具执行」各自在哪一行

---

## 7. 常见坑（提前打预防针）

1. **`function_call` 的 `arguments` 是字符串**，必须 `json.loads`，直接当 dict 用会报错。
2. **别忘把 `resp.output` 追加回 input**——尤其 `function_call` 本身也要放回去，否则模型"失忆"（或报 `No tool call found for function call output`）。
3. **`call_id` 要匹配**：`function_call_output` 里的 `call_id` 必须和你执行的那个 `function_call.call_id` 一致。用 `previous_response_id` 能少踩这个坑。
4. **必须有 `max_steps`**，否则模型可能无限调工具（尤其是工具报错时反复重试）。
5. **`required` 别漏填**——漏了模型可能不传关键参数。
6. **工具 `description` 写不清楚 = 模型乱调**——Agent 调试的第一现场，往往不是改代码，是改描述。
7. **token 每轮都累积**——循环里每次都把全部历史重发，任务越长越费钱，这就是为什么后续要学「记忆管理」。

---

*本指南基于 OpenAI Responses API（`openai` SDK，`client.responses.create`）。若用国内模型（DeepSeek/通义/智谱等）请确认是否支持 Responses API，否则改用 Chat Completions 写法。配套阅读：`smolagents源码阅读指南.md`（同目录）第 3、6 节。*
