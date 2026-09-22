# 倒着拆 smolagents：从 200 行脚本到框架内核（详细实现版）

> **写给**：已经手写出最小 Agent 循环（`work/Minimum Agent loop/test.ipynb`），但打开 `smolagents/src/smolagents/agents.py` 就懵的人。
>
> **本文主张**：你不需要"读懂"smolagents。你需要**把它倒着拆开、在你自己的代码里重新发明一遍**——但是阉割版。
>
> **本版新增**：每个要实现的类和方法都有完整规格说明——它是什么、为什么需要它、参数和返回值、具体做哪几步、边界情况、怎么自己验证。**假设你从没写过类、装饰器、生成器。**
>
> 基于本地克隆的 smolagents `v1.27.0.dev0`（commit `30bb116`）编写。行号可能随版本漂移，但抽象没变。

---

## 目录

- [0. 开始之前](#0-开始之前)
- [第 1 拆｜把「两份要同步的 dict」变成 `Tool` 基类](#第-1-拆把两份要同步的-dict-变成-tool-基类)
- [第 2 拆｜把「函数里的 for」变成「生成器 + 步骤对象」](#第-2-拆把函数里的-for-变成生成器--步骤对象)
- [第 3 拆｜加第二个 Agent，逼出抽象基类](#第-3-拆加第二个-agent逼出抽象基类)
- [第 4 拆｜泛化税分类](#第-4-拆选做泛化税分类学会跳过-60-的代码)
- [附录 A｜语法速查](#附录-a语法速查卡住时翻这里)
- [附录 B｜查源码的姿势](#附录-b查源码的正确姿势)
- [附录 C｜总验收](#附录-c总验收)

---

## 0. 开始之前

### 0.1 为什么"读"没用，"拆"有用

你已经有一份《smolagents 源码阅读指南》了，它写得不错——模块职责、阅读顺序、`pyproject.toml` 科普都到位。但它没帮你跨过最后一步，原因是：

> **那份指南让你当"读者"，而你现在需要当"作者"。**

读者视角看到的是"这段代码为什么这么长"。作者视角看到的是"我如果不这么写，会遇到什么麻烦"。**你缺的不是知识，是那个"被逼到不得不这么设计"的体验。**

### 0.2 三条铁律

1. **不改源码，只改自己的代码。** 全程在你自己新建的 `.py` 文件里做，`smolagents/` 目录只用来"事后对照"，一行都不许动。
2. **每拆必须跑通再进下一拆。** 每拆末尾有「自测脚本」和「检验问题」——前者是机器判卷，后者是自问。
3. **看不懂就跳过，并且理直气壮。** smolagents 12846 行里，**60% 以上是"泛化税"**——为了让框架同时支持几十种模型、流式/非流式、远程沙箱、定时规划而付出的代价。那是产品功能，不是 Agent 原理。跳过它们不丢人，是正确操作。

### 0.3 时间预算

| 拆分 | 内容 | 预算 |
|---|---|---|
| 第 1 拆 | 工具注册：dict → `Tool` 基类 | 半天 |
| 第 2 拆 | 主循环：函数 → 生成器 + 步骤对象 | 半天到一天 |
| 第 3 拆 | 抽象：一个 Agent → 两个 Agent + 抽象基类 | 一天 |
| 第 4 拆 | （选做）泛化税分类 | 一小时 |

**总共 2-3 天。做完立刻回到路线图的阶段 2（RAG）。** 阶段 2 和这件事完全正交，可以并行——白天做 RAG，晚上做这个。**不要为这件事单独开一周。**

### 0.4 准备

```bash
cd C:/Users/zzb/Desktop/py/agent/smolagents
pip install -e ".[openai]"
```

建工作目录 `work/rebuild/`，里面放三个文件：

```
work/rebuild/
├── tools_base.py     # 第 1 拆产物
├── agent_core.py     # 第 2 拆产物
└── agents_v2.py      # 第 3 拆产物
```

**建议用 `.py` 文件而不是 notebook**：你需要继承、模块导入、装饰器，notebook 的单元格执行顺序会把这些搞乱。

### 0.5 怎么用这份文档

每一拆都是同一个节奏：

```
1.1 你现在的写法      → 把你 notebook 里的原始代码贴出来
1.2 它疼在哪          → 为什么这个写法会出问题
1.3 拆完长什么样      → 目标 API 的全貌（先看整体）
1.4 要实现的清单      → 一张表，知道要做几件事
1.5 逐个方法详细规格  → ★ 主体。每个方法：是什么/为什么/参数/步骤/边界/自测
1.6 自测脚本          → 直接复制粘贴运行，全绿才算过
1.7 对照源码          → 现在再去看 smolagents，你会发现全是熟人
1.8 ✅ 检验问题        → 自问，答不出就回去重做
```

**我不会给你完整代码。** 因为你要练的是"自己写出来"，不是"照着抄一遍"。但每个方法的规格足够详细，照着规格你一定写得出来。**真的卡死了就来问我，我可以只给你那一个方法。**

---

## 第 1 拆｜把「两份要同步的 dict」变成 `Tool` 基类

### 1.1 你现在的写法

```python
tools : list = []
tool_func : dict[str:Callable] = {}

tools.append(create_schema(
    name = "get_weather",
    description = "查询某城市的当前天气",
    properties = {"city": {"type": "string", "description": "城市名"}},
    required = ["city"],
))
tool_func["get_weather"] = get_weather          # ← 手动同步

# 调用时：
result = tool_func[tool_call.name](**args)
```

### 1.2 它疼在哪

**同一个工具的信息散在三个地方**：函数名 `get_weather`、schema 里的 `"get_weather"`、字典的 key `"get_weather"`。加第四个工具时三处都要改；改错一处，报错发生在**运行时**，而且是 `KeyError` 而不是"你 schema 写错了"。

更要命的是：**给模型看的 `description` 和你真实的函数，语义上没有任何强制联系。** 你改了函数行为忘了改描述，模型就会拿到错误信息——而这类 bug 极难发现。

### 1.3 拆完长什么样

```python
from tools_base import Tool, tool

# 写法 A：类式（适合复杂工具）
class WeatherTool(Tool):
    name = "get_weather"
    description = "查询某城市的当前天气"
    inputs = {"city": {"type": "string", "description": "城市名"}}

    def forward(self, city: str) -> str:
        ...  # 你的 requests 代码

# 写法 B：装饰器式（适合简单函数）
@tool
def get_cur_time() -> str:
    """查询当前时间。"""
    return time.strftime("%X")

# 统一注册与调用
tools = [WeatherTool(), get_cur_time]
tools_by_name = {t.name: t for t in tools}        # ★ 只有一份，不再手动同步
schemas = [t.to_schema() for t in tools]          # ★ 自动生成给模型的工具描述

# Agent 调用时：
result = tools_by_name[tool_call.name](**arguments)   # ★ 靠 __call__ 统一入口
```

**核心变化：工具从"散落的字典"变成了"对象"。** 信息附着在对象自己身上，不再有需要手动保持同步的第二份。

### 1.4 要实现的清单

| # | 名字 | 类型 | 难度 |
|---|---|---|---|
| 1 | `Tool` 基类 | 类 | ★★ |
| 2 | `Tool.forward()` | 抽象方法 | ★ |
| 3 | `Tool.__call__()` | 魔法方法 | ★ |
| 4 | `Tool.to_schema()` | 普通方法 | ★★ |
| 5 | `WeatherTool` / `CurTimeTool` / `ExchangeRateTool` | 三个子类 | ★ |
| 6 | `python_type_to_json_type()` | 辅助函数 | ★ |
| 7 | `tool()` | 装饰器 | ★★★ |

### 1.5 逐个方法的详细规格

---

#### 1.5.1 `Tool` 基类 —— 三个类属性

```python
from abc import ABC, abstractmethod

class Tool(ABC):
    name: str
    description: str
    inputs: dict[str, dict]
```

**它是什么**：所有工具的"父类"。它不是任何具体工具，而是规定"**一个工具必须长什么样**"。

**三个类属性逐个解释**：

**① `name: str` —— 注意，这里只有类型声明，没有赋值！**

```python
name: str          # ✅ 只有声明，子类必须自己填
# name = ""        # ❌ 不要这样写
```

为什么？因为 `name = ""` 是个**安静的默认值**——子类忘了填，程序照跑，只是模型看到的名字是空字符串，排查起来很痛苦。而 `name: str` 不给值，子类忘了填，访问 `self.name` 时直接 `AttributeError`，**当场就炸，炸在你写代码的那天而不是上线的那天**。

> 这是"让错误尽早暴露"的经典手法。smolagents 的 `tools.py:99` 就是这么写的。

**② `description: str` —— 这是给模型看的，不是给人看的**

它不是注释。它会被拼进 system prompt 里，模型**只能靠这句话**判断"什么时候该用这个工具"。所以要写清楚"这工具干什么、什么场景该用"，而不是"查询天气"这种含糊话。

**③ `inputs: dict[str, dict]` —— 参数的"方便格式"**

```python
inputs = {
    "city": {
        "type": "string",              # 参数的 JSON Schema 类型
        "description": "城市名，如「北京」",
        "required": True,              # 可选，不写默认 True
    },
    "unit": {
        "type": "string",
        "description": "温度单位",
        "required": False,
    },
}
```

**为什么要有这个"方便格式"**：直接写标准 JSON Schema 又长又绕（下面 1.5.4 会看到差别）。用一个更简单的格式给人写，再由 `to_schema()` 翻译成标准格式——**这一层"翻译"本身就是重点**，smolagents 里那个翻译层就是 `_function_type_hints_utils.py`（431 行，干的全是这件事）。

**为什么要 `(ABC)`**：`ABC` = Abstract Base Class。加上它，`Tool()` 就不能被直接实例化了——因为"一个工具"这个概念本身没有意义，只有"查询天气工具"才有意义。**它防止你写出 `Tool()` 这种必然是 bug 的代码。**

---

#### 1.5.2 `Tool.forward()` —— 抽象方法

```python
class Tool(ABC):
    ...

    @abstractmethod
    def forward(self, **kwargs) -> str:
        """真正干活的代码。子类必须实现。"""
        ...
```

**它是什么**：抽象方法。**只有签名和文档，没有实现**，函数体写 `...`。

**为什么需要它**：因为基类要"规定子类必须提供一个干活的方法"，但基类自己不知道该怎么干活。`@abstractmethod` 的作用是：**只要有子类没实现 `forward`，实例化时就直接报错。**

**参数**：`**kwargs` —— 因为工具的参数是**按名字传**的（模型给的是一个 JSON 对象 `{"city": "北京"}`），不同工具参数个数不同，所以用 `**kwargs` 收集。

**返回**：`str` —— 简单版统一返回字符串。这个字符串会被塞回对话历史给模型看，所以**要写成人能读懂的一段话**，而不是裸的 JSON。

**写 `...` 而不是 `pass`**：这是 Python 惯例，语义是"这里**故意**空着"，而 `pass` 读起来像"我忘了写"。

**为什么名字叫 `forward` 而不是 `run` / `execute`**：这是 smolagents 的命名（`tools.py:108`），我们照抄，方便你之后对照。实际含义就是"工具被调用时要执行的动作"。

**自测**：
```python
try:
    Tool()          # 应该报错
    print("❌ 不该能实例化")
except TypeError as e:
    print("✅ ABC 拦住你了：", e)
```

---

#### 1.5.3 `Tool.__call__()` —— 魔法方法

```python
class Tool(ABC):
    ...

    def __call__(self, **kwargs) -> str:
        return self.forward(**kwargs)
```

**它是什么**：`__call__` 是 Python 的**魔法方法**之一，它定义了"把对象当函数调用"时发生什么。

```python
w = WeatherTool()
w(city="北京")            # ← 等价于 w.__call__(city="北京")
```

**为什么需要它（这题很重要）**：

Agent 手里是一个 `dict[str, Tool]`，里面装着**结构完全不同的各种工具**。Agent 拿到模型给的 `tool_call.name` 和 `tool_call.arguments` 之后，最自然的调用方式是：

```python
tools_by_name[tool_call.name](**tool_call.arguments)
```

注意最后那对括号——**它要求"工具对象本身可以被调用"**。如果没有 `__call__`，Agent 就得写成：

```python
tools_by_name[tool_call.name].forward(**tool_call.arguments)   # ❌ 太丑
```

后者的问题是：**Agent 必须知道"工具的内部有一个叫 forward 的方法"**。这个知识不该泄漏到 Agent 那里——万一以后某个工具不用 `forward` 呢？Agent 就得写 if-else。

**有了 `__call__`，Agent 只需要知道"工具可以被调用"这一件事。** 这叫**接口**：调用方和实现方之间的一份最小契约。

**以后你能在这里加什么**（现在不用写，知道位置留好了就行）：
- 参数校验（模型给了个不存在的参数名？在这里拦下）
- 日志（"工具 X 被调用了，参数 Y"）
- 懒加载（第一次调用时才初始化，见 smolagents 的 `setup`，`tools.py:126`）
- 计时（这个工具花了多久）

**注意 `**kwargs` 不是 `*args`**：工具调用永远是按名字传参的，模型给的是 JSON object。用 `*args` 你就拿不到参数名了。

---

#### 1.5.4 `Tool.to_schema()` —— 把"方便格式"翻译成"标准格式"

```python
class Tool(ABC):
    ...

    def to_schema(self) -> dict:
        """把自己翻译成 OpenAI Responses API 要的 function 工具描述。"""
```

**它是什么**：格式翻译器。把 `self.inputs`（你写的"方便格式"）翻译成 API 要求的**标准 JSON Schema**。

**为什么要单独一个方法**：因为"给人写的格式"和"给机器写的格式"不该是同一个。就像你会用 YAML 写配置，但程序内部读的是 dict。

**返回什么**：必须长这样（这是 OpenAI Responses API 的格式）：

```python
{
    "type": "function",
    "name": "get_weather",
    "description": "查询某城市的当前天气",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名"}
        },
        "required": ["city"]           # ★ 注意这里是数组，且在 parameters 这一层
    }
}
```

**具体做哪几步**：

1. 遍历 `self.inputs.items()`，对每个参数：
   - 复制一份参数的 dict（**别改原对象**！用 `dict(v)` 或 `{**v}`）
   - 从副本里**摘出** `required` 这个键（`pop("required", True)`），把参数名记到 `required_list` 里
   - 剩下的部分就是标准的 property 定义
2. 返回上面那个结构

**⚠️ 最大的坑**：JSON Schema 里，`required` **不是每个参数里的布尔值，而是 `parameters` 这一层的字符串数组**。

```python
# 你写的方便格式（错的 JSON Schema）：
"city": {"type": "string", "required": True}

# 标准的 JSON Schema（对的）：
"properties": {"city": {"type": "string"}},
"required": ["city"]
```

**这个坑是真实存在的**，很多人第一次手写工具都会踩。`to_schema()` 存在的全部意义，就是把这件事**只做一次、并且做对**。

**边界情况**：
- 工具没有参数（比如 `get_cur_time`）→ `properties` 是 `{}`，`required` 是 `[]`。**注意是空数组，不是省略这个键。**
- 用 `pop` 时要给默认值 `True`，不然没写 `required` 的参数会漏掉。

**自测**：
```python
s = WeatherTool().to_schema()
assert s["type"] == "function"
assert s["name"] == "get_weather"
assert s["parameters"]["required"] == ["city"]
assert s["parameters"]["properties"]["city"]["type"] == "string"
assert "required" not in s["parameters"]["properties"]["city"]   # ★ 必须被摘掉
assert s["parameters"]["properties"]["city"]["description"] == "城市名"
```

---

#### 1.5.5 三个工具子类

把 `test.ipynb` 里那三个函数搬过来，各包一个类：

| 类名 | `name` | `inputs` | 说明 |
|---|---|---|---|
| `WeatherTool` | `"get_weather"` | `city`（必填） | 网络请求查天气 |
| `CurTimeTool` | `"get_cur_time"` | 无 | 本地时间 |
| `ExchangeRateTool` | `"get_exchange_rate"` | `base`、`quote`（都必填） | 你原来的假数据版本就行 |

**`forward` 的签名要和 `inputs` 一致**：

```python
class ExchangeRateTool(Tool):
    name = "get_exchange_rate"
    description = "查询两种货币之间的汇率"
    inputs = {
        "base":  {"type": "string", "description": "基础货币，如 CNY"},
        "quote": {"type": "string", "description": "目标货币，如 USD"},
    }

    def forward(self, base: str, quote: str) -> str:
        return f"1 {base} = 7.2 {quote}"
```

**这里有个设计问题留给你想**：`inputs` 里写了参数名，`forward` 的签名里又写了一遍。**这两份信息还是重复的**——那为什么不干脆从 `forward` 的签名自动生成 `inputs`？（答案在 1.5.7 的装饰器里，你现在可以先把这个问题记住。）

---

#### 1.5.6 `python_type_to_json_type()` —— 辅助函数

```python
def python_type_to_json_type(annotation) -> str:
    """把 Python 的类型注解翻译成 JSON Schema 的类型字符串。"""
```

**它是什么**：一张翻译表 + 一次查表。

```python
_PY_TO_JSON = {
    str:   "string",
    int:   "integer",
    float: "number",
    bool:  "boolean",
    list:  "array",
    dict:  "object",
}
```

**做什么**：
1. 如果 `annotation` 在表里 → 返回对应字符串
2. 不在表里 → `raise TypeError(f"不支持的类型注解：{annotation}")`

**为什么单独抽一个函数**：装饰器里要用、以后可能别的地方也要用；而且以后要扩展（比如 `list[str]` 应该翻译成 `{"type": "array", "items": {"type": "string"}}`）时，只改这一个地方。

**⚠️ 一个大坑（这个坑很值钱）**：

```python
# ❌ 错的写法
if annotation == int: return "integer"
if annotation == bool: return "boolean"

# ✅ 对的写法：用注解对象本身当字典的 key
if annotation in _PY_TO_JSON: return _PY_TO_JSON[annotation]
```

**为什么**：在 Python 里 `bool` 是 `int` 的子类！`isinstance(True, int)` 是 `True`。如果你用 `isinstance` 去判断类型，`bool` 会被误判成 `integer`。用 `annotation in 字典` 这种**精确匹配**（字典的 key 比较用的是 `==` 和 `hash`，类对象之间不会串）就不会有事。

**为什么这题值钱**：这类"语言的隐蔽规则"就是读源码时最容易被绊倒的地方。smolagents 的 `_function_type_hints_utils.py` 里有大段代码在处理各种类型注解的边界情况——**你现在遇到的是同一个问题的迷你版。**

**自测**：
```python
assert python_type_to_json_type(str) == "string"
assert python_type_to_json_type(bool) == "boolean"    # ★ 不能是 "integer"
try:
    python_type_to_json_type(object)
    print("❌ 应该报错")
except TypeError:
    print("✅")
```

---

#### 1.5.7 `tool()` —— 装饰器（本拆最难的一个）

```python
def tool(fn: Callable) -> Tool:
    """把一个普通函数包装成 Tool 实例。"""
```

**先搞懂"装饰器"是什么**

```python
@tool
def get_cur_time() -> str:
    """查询当前时间。"""
    return time.strftime("%X")
```

上面这段 `@tool` 语法，**完全等价于**：

```python
def get_cur_time() -> str:
    """查询当前时间。"""
    return time.strftime("%X")

get_cur_time = tool(get_cur_time)      # ★ 就是这一行
```

**看明白了吗**：装饰器就是"把函数传进去，把某个东西赋值回同一个名字"。就这么简单。

所以 `@tool` 执行完之后，名字 `get_cur_time` **不再指向原来的函数**，而是指向 `tool()` 返回的东西。**这就是为什么 `tool()` 的返回类型注解写的是 `-> Tool` 而不是 `-> Callable`。**

**它是什么**：把"一个带类型注解和 docstring 的函数"自动转换成一个 `Tool` 实例，让用户不用手写 `inputs` 和 `description`。

**为什么要它**：因为 1.5.5 末尾留的那个问题——`inputs` 和 `forward` 签名重复了。装饰器的思路是：**既然函数签名里已经有参数名和类型注解，docstring 里已经有描述，那就从它们自动生成，别让人写第二遍。**

**参数**：一个函数。**要求**：必须有类型注解（每个参数有，返回值也有）+ 有 docstring。

**返回**：一个 `Tool` 的**实例**（不是类，不是原函数）。

**具体做哪几步**：

**第 1 步：读签名**
```python
sig = inspect.signature(fn)
```
`sig.parameters` 是一个有序字典：`{参数名: Parameter对象}`。每个 `Parameter` 有两个关键属性：
- `.annotation` —— 类型注解。没写就是 `inspect.Parameter.empty`
- `.default` —— 默认值。没默认值就是 `inspect.Parameter.empty`

**第 2 步：读描述**
```python
description = (fn.__doc__ or "").strip().split("\n")[0]
```
取 docstring 第一行当描述。（进阶：解析 `Args:` 段落给每个参数写描述——**先别做，用参数名当描述就行**。）

**第 3 步：遍历参数，构建 `inputs`**
```python
inputs = {}
required = []
for pname, param in sig.parameters.items():
    if param.annotation is inspect.Parameter.empty:
        raise TypeError(f"参数 {pname} 缺少类型注解，@tool 需要它来生成 schema")
    inputs[pname] = {
        "type": python_type_to_json_type(param.annotation),
        "description": pname,           # 简单版：用参数名当描述
    }
    if param.default is inspect.Parameter.empty:
        required.append(pname)
    else:
        inputs[pname]["required"] = False
```

**注意 `is inspect.Parameter.empty` 而不是 `== empty`** —— 判断"是不是那个特殊的空标记"要用 `is`（同一性），`==` 可能被重载出意外行为。

**第 4 步：动态创建一个子类**

这是本方法最"魔法"的一步。你不能在写代码时就写好这个子类，因为它是**运行时才知道**的（函数名、参数都是运行才知道的）。所以：

```python
class SimpleTool(Tool):
    name = fn.__name__
    description = description
    inputs = computed_inputs

    def forward(self, **kwargs) -> str:
        return fn(**kwargs)

return SimpleTool()
```

**这段代码写在 `tool()` 函数内部**，所以每次调用 `tool()` 都会创建一个**新的类**。这是有意的（每个函数得到自己的子类）。

**第 5 步：返回实例**
```python
return SimpleTool()
```

**⚠️ 三个必须搞清楚的坑**

**坑 1：返回的是实例，不是类。**
```python
print(type(get_cur_time))        # <class 'tools_base.SimpleTool'>  —— 是个实例
print(get_cur_time(city="北京")) # 能直接调用，说明 __call__ 生效了
```
调用链是这样的：
```
get_cur_time(city="北京")
  → SimpleTool.__call__(city="北京")      ← 1.5.3 那个方法
  → SimpleTool.forward(city="北京")       ← 第 4 步写的
  → fn(city="北京")                       ← 你原来的函数
```
**看清楚了吗**——`__call__` 和 `forward` 都是你自己写的，现在它们在真实地工作。

**坑 2：`forward(self, **kwargs)` 丢掉了真实签名。**
这是简单版的妥协。真实版会把原函数的签名"贴"回 `forward` 上（smolagents 用 `__signature__` 做到这件事，见 `tools.py:1104-1110`）——**那是元编程，现在跳过，不影响你理解整体。**

**坑 3：装饰器里报错会让模块导入失败。**
如果某个函数忘了写类型注解，`@tool` 会在**模块被 import 的那一刻**就抛 `TypeError`。这是好事——**错误暴露得越早越好**。对比一下：如果你不用装饰器，忘了写类型注解的后果可能是运行时模型收到了错误的 schema，你查半天。

**自测**：
```python
@tool
def add(a: int, b: int = 1) -> int:
    """把两个数相加。"""
    return a + b

assert isinstance(add, Tool)                 # 是 Tool 的实例
assert add.name == "add"
assert add.description == "把两个数相加。"
assert add.inputs["a"]["type"] == "integer"
assert add.inputs["a"].get("required", True) is True
assert add.inputs["b"]["required"] is False   # 有默认值 → 非必填
assert add(a=1, b=2) == 3                     # 能正常调用
assert add.to_schema()["parameters"]["required"] == ["a"]
```

### 1.6 第 1 拆综合自测脚本

复制到文件末尾直接跑（**不需要 API key，纯本地**）：

```python
if __name__ == "__main__":
    # --- 基类层面 ---
    try:
        Tool(); raise SystemExit("❌ Tool() 不该能实例化")
    except TypeError:
        pass

    # --- 类式工具 ---
    w = WeatherTool()
    assert w.name == "get_weather"
    assert w(city="北京").startswith("北京")
    s = w.to_schema()
    assert s["parameters"]["required"] == ["city"]
    assert "required" not in s["parameters"]["properties"]["city"]

    # --- 无参数工具 ---
    t = CurTimeTool()
    ts = t.to_schema()
    assert ts["parameters"]["properties"] == {}
    assert ts["parameters"]["required"] == []
    assert ":" in t()

    # --- 装饰器工具 ---
    assert isinstance(get_cur_time, Tool)
    assert type(get_cur_time).__name__ == "SimpleTool"
    assert get_cur_time.name == "get_cur_time"

    # --- 统一注册与调用（模拟 Agent 的行为）---
    tools = [WeatherTool(), CurTimeTool(), ExchangeRateTool(), get_cur_time]
    tools_by_name = {x.name: x for x in tools}
    schemas = [x.to_schema() for x in tools]
    assert len(schemas) == 4
    assert tools_by_name["get_weather"](city="上海").startswith("上海")
    assert "7.2" in tools_by_name["get_exchange_rate"](base="CNY", quote="USD")

    print("✅ 第 1 拆全部通过")
```

### 1.7 对照源码

做完再看这几处，**你会发现全是熟人**：

| 位置 | 看什么 | 你的对应物 |
|---|---|---|
| `tools.py:98` `class BaseTool(ABC)` | 它只有 `__call__` 一个抽象方法，`name: str` 只是类型声明没赋值 | 你的 `Tool` |
| `tools.py:106` `class Tool(BaseTool)` | `name`/`description`/`inputs`/`output_type` 是**类属性**，子类直接赋值 | 你的 `Tool` |
| `tools.py:140` `__init_subclass__` | 子类**被定义时**自动跑校验。**它替你做了"我写完忘填 description"的检查** | 你暂时没做 |
| `tools.py:1061-1101` `def tool(...)` | 关键在 1080-1101：动态创建 `SimpleTool(Tool)`，给类属性赋值，最后 `return SimpleTool()` | 你的 `tool()` 装饰器 |
| `_function_type_hints_utils.py` | `get_json_schema()`——你的 `to_schema()` + `@tool` 的工业版 | ★ 重点对照 |

> **为什么 smolagents 要多一个 `BaseTool`？** 你的 `Tool` 一层就够了。多出来的那层是为了让 `ToolCollection` / MCP 工具等**不是普通 Python 函数**的工具也能接入——**又是泛化税。** 你现在用不着。

> ⚠️ `tools.py:1101` 的 `SimpleTool.forward = staticmethod(...)` 和 1106-1110 的 `__signature__` 改写是**元编程**，属于 A 类里的硬骨头。**现在跳过。**

### 1.8 ✅ 检验问题（第 1 拆）

1. **`Tool.__call__` 里做了什么？为什么不干脆让 Agent 直接调 `tool.forward()`？**
   （提示：Agent 手里是一堆**异构**工具，它需要一个统一入口。另外 `__call__` 以后还能顺便做参数校验、日志、懒加载）

2. **`@tool` 装饰器返回的到底是类还是实例？**
   敲 `print(type(get_cur_time))` 验证。然后回答：`get_cur_time(city="北京")` 这一行调用，**依次经过了哪几个函数**？请按顺序写出来。

3. **为什么 `name: str` 只写声明不写赋值？** 如果写成 `name = ""`，出问题时你会看到什么现象？排查难度有什么变化？

4. **`to_schema()` 里为什么必须把 `required` 从 properties 里摘出来？** 如果你不摘，直接原样塞进 properties，模型会收到什么？（提示：这是"你写的格式"和"JSON Schema 标准"的差别）

5. **`python_type_to_json_type` 为什么不能用 `isinstance` 判断？** `bool` 和 `int` 是什么关系？你写一句代码验证一下。

6. **你的 `@tool` 遇到一个没写返回类型注解的函数会怎样？**
   去 `tools.py:1072-1078` 看 smolagents 怎么处理。**它为什么选择直接报错，而不是猜一个类型？**

7. **`get_cur_time` 没有任何参数。** 它的 `inputs` 是什么？`properties` 和 `required` 分别是什么？——写个 assert 验证。

8. **`SimpleTool` 定义在 `tool()` 函数内部，每次调用 `@tool` 都创建一个新类。** 用 `type(get_cur_time) is type(add)` 验证一下（用 1.5.7 自测里的 `add`）。**为什么这样设计？**（提示：如果所有工具共用一个类，`name`/`description` 放哪？）

---

## 第 2 拆｜把「函数里的 for」变成「生成器 + 步骤对象」

**这是最重要的一拆。** 做完它，`agents.py` 的主循环对你就不再是黑箱。

### 2.1 你现在的写法

```python
def run_agent(task: str, max_step: int = 5) -> str:
    input : list = []
    input.append({"role": "user", "content": [{"type": "input_text", "text": task}]})
    resp : Response = None
    for step in range(max_step):
        resp = client.responses.create(
            input=input, instructions="...", model="deepseek-flash", tools=tools,
        )
        input += resp.output
        tool_calls = [i for i in resp.output if i.type == "function_call"]
        if not tool_calls:
            return "最终答案:" + resp.output_text
        for tool_call in tool_calls:
            args = json.loads(tool_call.arguments)
            result = tool_func[tool_call.name](**args)
            input.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result,
            })
    return "模型没有找到答案"
```

### 2.2 它疼在哪

三个独立的痛，都指向同一个解法：

**痛 1：中间过程被 `print` 写死了。** 想看每一步、想存日志、想在前端实时显示——只能改 `run_agent` 内部。**"观察循环过程"变成了"修改循环实现"。**

**痛 2：信息散在局部变量里。** `resp`、`tool_calls`、`result` 都活不过一轮迭代，跑完什么都不剩。想回溯"第 3 步为什么失败了"——没数据。

**痛 3：`input` 是手工维护的。** `input += resp.output`、`input.append({...})`——**你在手工维护对话历史**。而历史恰恰是 Agent 最重要的状态。

### 2.3 拆完长什么样

```python
@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: str
    result: str | None = None

@dataclass
class ActionStep:
    step_number: int
    model_output_items: list = field(default_factory=list)
    model_output: str | None = None
    tool_calls: list[ToolCall] | None = None
    observations: str | None = None
    error: Exception | None = None
    is_final_answer: bool = False

class AgentMemory:
    def __init__(self, task: str): ...
    def reset(self): ...
    def append(self, step: ActionStep): ...
    def to_messages(self) -> list[dict]: ...      # ★ 从 steps 反推出 API 要的 input

class Agent:
    def __init__(self, tools, model, max_steps=5, instructions=""): ...
    def _step_stream(self, step: ActionStep) -> Generator: ...      # 一步之内做什么
    def _run_stream(self, task, max_steps) -> Generator: ...        # 步骤之间怎么循环
    def run(self, task, stream=False, max_steps=None): ...
    def _handle_max_steps_reached(self, step_number) -> ActionStep: ...
```

**三个认知升级，全在这一拆：**

- **A. 循环过程变成"可被外部消费的数据流"**（生成器）。想看就 `for step in agent.run(task, stream=True)`，不想看就 `agent.run(task)`。**同一个循环，两种消费方式。**
- **B. 每一步变成一个对象**（`ActionStep`）。信息不再蒸发，可以存、可以 dump、可以回放。
- **C. `input` 不再手工维护，而是从 memory 推导**（`memory.to_messages()`）。**这是最关键的一步**——对话历史从"随手 append 的副产物"变成了"一等公民状态"。

### 2.4 要实现的清单

| # | 名字 | 类型 | 难度 |
|---|---|---|---|
| 1 | `ToolCall` | dataclass | ★ |
| 2 | `ActionStep` | dataclass | ★★（字段多，但都是死记） |
| 3 | `ActionStep.to_messages()` | 方法 | ★★★ |
| 4 | `AgentMemory` | 类（4 个方法） | ★★ |
| 5 | `Agent.__init__` | 初始化 | ★ |
| 6 | `Agent._step_stream()` | **生成器** | ★★★★★ |
| 7 | `Agent._run_stream()` | **生成器** | ★★★★★ |
| 8 | `Agent.run()` | 方法 | ★★ |
| 9 | `Agent._handle_max_steps_reached()` | 方法 | ★★ |

### 2.5 逐个方法的详细规格

---

#### 2.5.1 `ToolCall` —— 记录"模型想调什么"

```python
@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: str
    result: str | None = None
```

**它是什么**：一个数据容器，代表"模型想调用某个工具"这一件事。

**`@dataclass` 是什么**：Python 的语法糖，自动帮你生成 `__init__`。写了 `@dataclass` 之后你就能直接 `ToolCall(name="x", arguments={}, call_id="y")`，不用自己写 `def __init__(self, name, arguments, call_id, result=None): self.name = name; ...`。

**四个字段逐个解释**：

| 字段 | 从哪来 | 为什么要它 |
|---|---|---|
| `name` | 模型的 `function_call.name` | 去 `tools_by_name` 里查该调哪个工具 |
| `arguments` | `json.loads(function_call.arguments)` | **注意要 `json.loads`**！模型返回的是 JSON **字符串**，不是 dict |
| `call_id` | `function_call.call_id` | **回填结果时必须带上它**。API 靠这个 ID 把"执行结果"和"当初的调用请求"配对。**多个工具同时调用时，没它就会串号** |
| `result` | 执行后回填 | 工具执行的结果。`None` 表示"还没执行"或"执行失败" |

**为什么 `result` 要放在 ToolCall 里**，而不是 step 上单独一个 list：**因为多个工具调用时，必须能一对一配对。** 如果 step 上是 `results: list[str]`，模型调了 3 个工具，你靠什么知道哪个结果属于哪个调用？靠顺序？——顺序是脆弱的假设。

**自测**：
```python
tc = ToolCall(name="get_weather", arguments={"city": "北京"}, call_id="call_1")
assert tc.result is None
assert tc.name == "get_weather"
```

---

#### 2.5.2 `ActionStep` —— 记录"走完了一步"

```python
from dataclasses import dataclass, field

@dataclass
class ActionStep:
    step_number: int
    model_output_items: list = field(default_factory=list)
    model_output: str | None = None
    tool_calls: list[ToolCall] | None = None
    observations: str | None = None
    error: Exception | None = None
    is_final_answer: bool = False
```

**它是什么**：一个"快照"，记录 Agent 走完一步之后的**全部信息**。你原来散在 `resp` / `tool_calls` / `result` 里的东西，现在都住进这一个对象。

**七个字段逐个解释（这是本拆最需要背下来的表）**：

| 字段 | 类型 | 存什么 | 为什么需要它 |
|---|---|---|---|
| `step_number` | `int` | 第几步，从 1 开始 | 日志里标号；判断有没有超过 `max_steps`；出问题时能说"第 3 步挂了" |
| `model_output_items` | `list` | 模型这轮返回的**原始 items 对象**（含 reasoning 和 function_call） | **回填给 API 时必须原样塞回去**。你原来那句 `input += resp.output` 干的就是这件事。**不要转换，存原始对象** |
| `model_output` | `str \| None` | 模型这轮的**纯文本**（`resp.output_text`） | **最终答案就是它**。另外调试时看它最直观 |
| `tool_calls` | `list[ToolCall] \| None` | 模型想调哪些工具 + 执行结果 | 核心字段 |
| `observations` | `str \| None` | 所有工具结果的**拼接摘要** | 只用于日志和"max_steps 兜底"时给模型看。**回填 API 时不用它**（用 `tool_calls[i].result`），因为拼接会丢失配对关系 |
| `error` | `Exception \| None` | 这一步**整体**失败了（比如 API 报错） | 区分"这步没做成"和"这步做成了"。不要用异常往外抛——**记下来，让循环继续** |
| `is_final_answer` | `bool` | 这步是不是最终答案 | **循环的退出条件**。整个 `_run_stream` 就靠它决定要不要停 |

**⚠️ 关于 `field(default_factory=list)`**

不能写 `model_output_items: list = []`！

```python
# ❌ 错误：所有 ActionStep 会共享同一个列表
model_output_items: list = []

# ✅ 正确
model_output_items: list = field(default_factory=list)
```

**为什么**：Python 的可变默认值只在**函数定义时求值一次**，所有实例共享同一个对象。你在 A 步骤里 append 一个元素，B 步骤里也会看到——这类 bug 极其隐蔽，因为单独测试时永远是对的。

**⚠️ 为什么 `step_number` 没有默认值**

因为它**必须**被显式提供。写在最前面（没有默认值的字段必须在有默认值的字段之前，这是 dataclass 的语法要求）。

**⚠️ 那些 `| None = None` 是什么意思**

`str | None` 就是 `Optional[str]`，"要么是字符串要么是 None"。`= None` 给了默认值，所以构造时可以省略。

**自测**：
```python
s1 = ActionStep(step_number=1)
s2 = ActionStep(step_number=2)
s1.model_output_items.append("x")
assert s2.model_output_items == []          # ★ 证明没有共享列表
assert s1.tool_calls is None
assert s1.is_final_answer is False
```

---

#### 2.5.3 `ActionStep.to_messages()` —— 把一步还原成对话消息

```python
def to_messages(self) -> list[dict]:
    """返回这一步要追加到对话历史里的所有消息。"""
```

**它是什么**：**本拆的灵魂方法**。它把"一个 ActionStep 对象"翻译成"要往 `input` 列表里追加的那几条消息"。

**为什么要它**：你原来手写了三件事：
```python
input.append({"role":"user", "content":[...]})           # ① 任务
input += resp.output                                     # ② 模型这轮输出
input.append({"type":"function_call_output", ...})       # ③ 工具结果
```
现在 ① 归 `AgentMemory.__init__`，②③ 归这个方法。**历史从"手工拼的列表"变成"从对象推导出来的列表"。**

**返回什么**：一个 list，元素是 API 能接受的 input item。

**顺序很重要，必须这样**：

```python
def to_messages(self) -> list[dict]:
    messages = []

    # 第 1 部分：模型这轮的原始输出，原样放回
    messages.extend(self.model_output_items)

    # 第 2 部分：每个工具调用一条结果消息
    for tc in (self.tool_calls or []):
        messages.append({
            "type": "function_call_output",
            "call_id": tc.call_id,
            "output": tc.result if tc.result is not None else "（未执行）",
        })

    return messages
```

**为什么必须原样放回 `model_output_items`**：
API 有个硬性要求——**`function_call_output` 前面必须能找到对应的 `function_call`**。你不把模型那轮的输出放回去，只放结果，API 会报错说"我不认识这个 call_id"。另外某些模型（比如带 reasoning 的）还要求把 reasoning item 也原样带回去。

**边界情况，一个个想清楚**：

**① `tool_calls is None`（模型这轮直接给了文字答案）**
→ 只返回 `model_output_items`，一条 `function_call_output` 都不返回。`(self.tool_calls or [])` 里的 `or []` 处理的就是这个。

**② 工具执行失败，`tc.result` 是错误信息**
→ 照常塞进去，`output` 就是那句 `"调用失败：xxx"`。**不要抛异常，也不要跳过。**
这是 **Agent 编程和普通编程最大的思维差别之一**：普通程序里"工具报错"是异常情况，要往上抛；Agent 里"工具报错"是**一种正常的信息**，要让模型看到，然后它下一轮会自己换个方式重试。**错误信息也是 prompt。**

**③ 多个工具调用**
→ 每个一条，`call_id` 保证配对。**顺序无所谓**，因为靠 ID 配不靠顺序。

**自测**（不需要 API）：
```python
step = ActionStep(step_number=1)
step.model_output_items = [{"type": "function_call", "name": "get_weather",
                            "arguments": "{}", "call_id": "c1"}]
step.tool_calls = [ToolCall(name="get_weather", arguments={}, call_id="c1", result="北京 晴")]
msgs = step.to_messages()
assert len(msgs) == 2
assert msgs[0]["type"] == "function_call"
assert msgs[1]["type"] == "function_call_output"
assert msgs[1]["call_id"] == "c1"
assert msgs[1]["output"] == "北京 晴"

# 边界：没有工具调用
step2 = ActionStep(step_number=2)
step2.model_output_items = [{"type": "message"}]
assert len(step2.to_messages()) == 1
```

---

#### 2.5.4 `AgentMemory` —— 对话历史的唯一所有者

```python
class AgentMemory:
    def __init__(self, task: str):
        self.task = task
        self.steps: list[ActionStep] = []

    def reset(self):
        self.steps = []

    def append(self, step: ActionStep):
        self.steps.append(step)

    def to_messages(self) -> list[dict]:
        messages = [{"role": "user", "content": [{"type": "input_text", "text": self.task}]}]
        for step in self.steps:
            messages.extend(step.to_messages())
        return messages
```

**它是什么**：Agent 的记忆。持有"任务 + 所有走过的步"。

**为什么单独一个类而不是 `self.steps = []`**：因为记忆有**行为**，不只是数据。`to_messages()` 就是那个行为。以后你还要加：
- `to_messages(keep_last_n=5)` —— 只保留最近 5 步，防止 token 爆炸（**你以后做长对话一定会需要这个**）
- `save(path)` / `load(path)` —— 持久化，下次接着跑
- `summary()` —— 让模型把长历史压缩成摘要

**四个方法逐个说**：

**`__init__(self, task)`**
- `self.task` 存任务原文。**为什么放在 memory 里而不是 Agent 上**：因为 `to_messages()` 的第一条永远是任务，它本质上是历史的第 0 条。
- `self.steps` 是空的 ActionStep 列表。

**`reset(self)`**
- 把 `steps` 清空。
- **为什么要有它**：同一个 Agent 对象要跑第二个任务时，必须先把上一次的记忆清掉，否则模型会看到上一个任务的对话。对应 smolagents 的 `reset` 参数（`agents.py:490-492`）。
- **注意**：`self.steps = []` 是**新建一个空列表**，不是 `self.steps.clear()`。两者效果在这里一样，但前者更安全（万一有别的变量引用着旧列表）。

**`append(self, step)`**
- 就是 `self.steps.append(step)`。
- 看起来是废话，但**它的意义在于"只有通过这个方法才能往记忆里加东西"**。第 3 拆里基类会规定："子类不许直接碰 `self.memory.steps`"——这就是职责分离。

**`to_messages(self) -> list[dict]`** ← ★ 核心
- 第一步：把任务变成一条 user 消息。
- 第二步：**按顺序**遍历 `self.steps`，把每个 step 的 `to_messages()` 结果拼进来。**顺序绝对不能乱**，因为对话历史是有序的。
- 用 `extend` 而不是 `append`——`append` 会把整个列表当成一个元素塞进去，得到嵌套列表。

**自测**：
```python
mem = AgentMemory("北京天气怎么样")
assert len(mem.to_messages()) == 1
assert mem.to_messages()[0]["role"] == "user"

mem.append(ActionStep(step_number=1, model_output_items=[{"type": "message"}]))
assert len(mem.to_messages()) == 2

mem.reset()
assert len(mem.to_messages()) == 1        # 回到只有任务那一条
assert mem.task == "北京天气怎么样"        # 任务不会被 reset 掉
```

---

#### 2.5.5 `Agent.__init__`

```python
class Agent:
    def __init__(self, tools: list[Tool], model: str, max_steps: int = 5, instructions: str = ""):
        self.tools = tools
        self.tools_by_name = {t.name: t for t in tools}
        self.tools_schema = [t.to_schema() for t in tools]
        self.model = model
        self.max_steps = max_steps
        self.instructions = instructions
        self.client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
        self.memory = AgentMemory("")      # 占位，run() 里会重建
```

**为什么要预先把 `tools_by_name` 和 `tools_schema` 算出来**：
这两样东西**在整个 run 过程中不会变**。如果每次调用工具都现算一遍，就是白干活。**这是"一次算好，反复使用"的常见优化**——也是为什么它们该在 `__init__` 里而不是 `_step_stream` 里。

**为什么 `tools` 用 list 而不是 dict 传进来**：因为调用方（你）写起来更自然（`[WeatherTool(), get_cur_time]`），转成 dict 是 Agent 的内部实现细节。

**`instructions`**：system prompt。你原来写死了 `"这是多工具调用的测试"`，现在做成参数。**这个参数很重要**，因为它直接决定模型的行为——第 3 拆里两个子类会传完全不同的 instructions。

---

#### 2.5.6 `Agent._step_stream()` —— ★★★★★ 本拆最难也最重要的方法

```python
def _step_stream(self, step: ActionStep) -> Generator:
    """执行一步：思考 → 行动 → 观察。中途 yield 出可以给外部看的东西。"""
```

**它是什么**：执行**一步**。

**先搞清楚"一步"是什么**：一步 = 一轮完整的 `思考 → 行动 → 观察`。**注意"一步"不等于"一次 LLM 调用"**——在 CodeAgent 里，一步里模型写的代码可能调用了 5 个工具。

**它和 `_run_stream` 的分工（这是第 3 拆的基础，务必看懂）**：

| | 负责什么 |
|---|---|
| `_step_stream` | **一步之内**做什么（业务逻辑） |
| `_run_stream` | **步骤之间**怎么循环（流程控制） |

**流程控制放基类，单步逻辑放子类**——第 3 拆的抽象基类就是按这条线切的。

**⚠️ 铁律：`_step_stream` 绝对不许碰 `self.memory`！**
不 append、不读 `steps`（读 `to_messages()` 可以，那是只读）。**改 memory 是 `_run_stream` 的职责。** 混在一起是第 3 拆抽不出基类的头号原因。

---

**具体做哪几步（按顺序，这个顺序不能乱）**：

**第 1 步：拿历史**
```python
input_messages = self.memory.to_messages()
```
注意是 `to_messages()` 而不是直接读 `self.memory.steps`。**永远通过方法读取，不直接摸内部数据。**

**第 2 步（可选但强烈建议）：把"模型看到了什么"记下来**
```python
step.model_input_messages = input_messages
```
这需要给 `ActionStep` 加一个字段。**为什么值得**：调试 Agent 时 90% 的问题都是"模型看到的东西和你想的不一样"。存下来，你随时能看。

**第 3 步：调模型**
```python
resp = self.client.responses.create(
    model=self.model,
    input=input_messages,
    instructions=self.instructions,
    tools=self.tools_schema,
)
```

**第 4 步：记录输出**
```python
step.model_output_items = list(resp.output)
step.model_output = resp.output_text
```
`list(...)` 是保险起见转成普通列表（SDK 返回的可能是别的序列类型）。

**第 5 步：解析工具调用**
```python
step.tool_calls = [
    ToolCall(
        name=o.name,
        arguments=json.loads(o.arguments),
        call_id=o.call_id,
    )
    for o in resp.output
    if o.type == "function_call"
]
```

**⚠️ 注意这里和你原来的写法的差别**：你原来用 `next(o for o in response.output if ...)` **只取第一个**，还配了句 instructions 说"一次回答仅调用一次工具"。这里改成**列表推导取全部**——因为：
- 第 3 拆的 CodeAgent 需要多个
- "一次只调一个工具"是模型的**行为约束**，不该由你的代码**结构性地**限制。你限制得太死，模型想并行查三个城市就做不到

**第 6 步：判断是不是最终答案**
```python
if not step.tool_calls:
    step.is_final_answer = True
    return
```

**⚠️ 生成器里的 `return` 是什么意思**：它**不是"返回一个值"**，而是"这个生成器到此结束"。你原来写的是 `return "最终答案:" + resp.output_text`，现在**返回值的活交给了 `step.model_output`**——因为结果要通过 step 对象传递，不能靠 return（生成器没有返回值）。

**这是个特别容易搞混的点，也是为什么你原来那个写法转不过来。**

**第 7 步：执行工具，回填结果，顺手 yield**
```python
for tc in step.tool_calls:
    try:
        tc.result = self.tools_by_name[tc.name](**tc.arguments)
    except Exception as e:
        tc.result = f"调用失败：{type(e).__name__}: {e}"
    yield tc
```

**⚠️ 这里 `except` 吞掉了所有异常，是故意的。** 模型调了一个不存在的工具 `get_wether`（拼错了）→ `KeyError` → 变成一条 `"调用失败：KeyError: 'get_wether'"` 给模型看 → 模型下一轮自己改。**这是特性不是 bug。**

**⚠️ 为什么在这里 `yield tc`**：工具调用可能很慢（查天气要发网络请求）。yield 出去，外部就能**实时**看到"第 1 个工具查完了"。如果这是个普通函数，你只能等所有工具跑完才看到结果。

**第 8 步：生成 observations 摘要**
```python
step.observations = "\n".join(
    f"{tc.name}({tc.arguments}) -> {tc.result}" for tc in step.tool_calls
)
```
只用于日志和 max_steps 兜底，**回填 API 时不用它**。

---

**几个必须想明白的设计问题**：

**Q1：为什么 `_step_stream` 是生成器而不是普通函数？**
因为一步内可能有多个耗时的工具调用，**外部需要能实时看到中间进度**。普通函数没有这个能力。

**Q2：`yield` 出来的东西，外部拿去干嘛？**
- `_run_stream` 拿到后**原样再 yield 出去**（这叫"生成器委托"）
- 最终到 `run(stream=True)` 的调用方手里，可以打印、可以推进前端进度条、可以写日志
- **如果不 yield，这些信息就被扔掉了**

**Q3：如果模型既给了文字又给了 tool_calls，怎么办？**
现在你的代码会**丢弃文字，以 tool_calls 为准**（因为 `if not step.tool_calls` 才结束）。
**这个决定要显式做出来**，别糊里糊涂。想一下：什么情况下模型会两者都给？丢掉文字对不对？

---

#### 2.5.7 `Agent._run_stream()` —— ★★★★★ 循环本体

```python
def _run_stream(self, task: str, max_steps: int) -> Generator:
    """循环跑步骤，逐步 yield 出去。"""
```

**它是什么**：**这就是"Agent 循环"四个字的源代码。** 你原来那段 `for step in range(max_step)` 就是它的雏形。

**它只做三件事，一件多的都不做**：

1. **循环**（什么时候继续、什么时候停）
2. **错误分流**（哪些错误记下来继续、哪些直接崩）
3. **记账**（把每步写进 memory）

**❗ 它不该含任何业务逻辑。** 如果你发现自己在 `_run_stream` 里写"如果模型说了 X 就 Y"，说明这段该挪到 `_step_stream` 去。**这是第 3 拆能不能抽出基类的关键。**

**具体做哪几步**：

```python
def _run_stream(self, task, max_steps):
    step_number = 1
    while step_number <= max_steps:
        step = ActionStep(step_number=step_number)
        try:
            for out in self._step_stream(step):
                yield out                    # ★ 生成器委托
        except Exception as e:
            step.error = e                   # ★ 记录而不中断
        finally:
            self.memory.append(step)
            yield step                       # ★ 无论成败都要被看见
            step_number += 1

        if step.is_final_answer:
            return

    yield self._handle_max_steps_reached(step_number)
```

**逐块拆解**：

**`while step_number <= max_steps`**
为什么不用 `for step_number in range(max_steps)`？—— 效果一样，`while` 更贴近 smolagents 的写法（`agents.py:557`），方便对照。用 `for` 也完全可以。

**`for out in self._step_stream(step): yield out`**
这叫**生成器委托**：把子生成器的每个产出**原样转发**出去。写起来啰嗦，但 Python 3.3+ 有个简写 `yield from self._step_stream(step)`——**效果完全一样，你可以用这个**。

**`except Exception as e: step.error = e`**
**这是本方法最需要理解的一行。** 注意它**没有 re-raise**——它把异常**吞掉并记录**。

为什么敢这样？因为：
- Agent 的主循环面对的是**不可靠的外部世界**（网络、模型、第三方 API）
- "这一步失败了"**不是**程序崩溃，是"模型的一次尝试没成功"
- 失败信息会通过 `step.error` 进入 `to_messages()`（第 2.5.3 节的边界情况②），**模型下一轮就能看到"上一步挂了，换个方式"**

**但这行在第 2 拆是过度简化。** 因为"API key 错了"和"工具超时了"都被一视同仁地吞掉了——前者你希望立刻崩掉。**第 3 拆会用异常家族把它修好**，这里先记着这个坑。

**`finally: ... yield step; step_number += 1`**
**为什么写在 `finally` 里而不是循环末尾**：
- 写在循环末尾 → 只有**成功**的路径会走到
- 写在 `finally` 里 → **成功和失败两条路都会走到**

因为"就算这步抛了异常，这一步也必须被记录、也必须被外部看见"。**异常也是一步。**

**⚠️ 一个已知小瑕疵**（知道就行，不用修）：把 `yield` 放进 `finally` 有个副作用——如果外部提前 `break` 掉生成器，Python 会往生成器里抛 `GeneratorExit`，而 `finally` 里的 `yield` 这时可能引发 `RuntimeError: generator ignored GeneratorExit`。

**smolagents 也是这么写的**（`agents.py:612-615`）。**这是"框架也有瑕疵"的现场教学**——你以后读任何库，都要保留"这里可能是将就的"这个判断力。

**`if step.is_final_answer: return`**
注意它在 `try/except/finally` **之后**。为什么不能放 try 里面？
因为 `finally` 一定会执行（`yield step` 在那儿），所以你必须在 finally 之后才检查。放前面会导致 check 在 yield 之前跑，逻辑就乱了。

**`return` vs `break`**：这里用 `break` 也一样，但 `return` 更明确地表达"整个生成器结束了"。**注意：生成器里的 `return` 不返回值**（同 2.5.6 第 6 步）。

**循环外的 `yield self._handle_max_steps_reached(step_number)`**
跑完 `max_steps` 还没有最终答案 → 走兜底路径。

**⚠️ 这里建立了整个设计最重要的一条不变量**：

> **`_run_stream` 保证：最后一个 yield 出来的 `ActionStep` 一定是 `is_final_answer=True`。**

有了这条不变量，`run()` 就能无脑取最后一步（2.5.8 会用到）。

**这条不变量正对应 smolagents 的 `assert isinstance(steps[-1], FinalAnswerStep)`（`agents.py:514`）。框架里的 `assert` 不是防别人，是防自己写错。**

**自测**：
```python
# 用一个假的 _step_stream 测试循环逻辑，不花 API 钱
class FakeAgent(Agent):
    def _step_stream(self, step):
        step.model_output_items = [{"type": "message"}]
        step.model_output = f"第{step.step_number}步"
        step.is_final_answer = (step.step_number >= 2)   # 第 2 步就结束
        return
        yield   # 让它是生成器

a = FakeAgent(tools=[], model="x")
steps = list(a._run_stream("测试", max_steps=5))
assert len(steps) == 2
assert steps[-1].is_final_answer is True
assert len(a.memory.steps) == 2

# 测异常路径
class BoomAgent(Agent):
    def _step_stream(self, step):
        raise ValueError("炸了")
        yield

b = BoomAgent(tools=[], model="x")
steps = list(b._run_stream("测试", max_steps=3))
assert len(steps) == 3                       # ★ 异常不中断循环
assert all(s.error is not None for s in steps)
assert steps[-1].is_final_answer is True     # ★ 兜底路径接住了
```

**这两段测试是本拆最有价值的自测**——它们不花一分钱 API，却验证了循环的全部骨架。**先让它们通过，再去调真 API。**

---

#### 2.5.8 `Agent.run()` —— 对外的唯一入口

```python
def run(self, task: str, stream: bool = False, max_steps: int | None = None) -> str:
```

**它是什么**：用户唯一需要调用的方法。**上面那堆 `_` 开头的方法都是内部实现，只有这个是对外的。**

**为什么要有这一层**：因为它做了三件用户不想操心的事——重置记忆、解析默认参数、决定返回什么。

**具体做哪几步**：

**第 1 步：解析 max_steps**
```python
max_steps = max_steps or self.max_steps
```
**⚠️ 这里有坑**：`or` 会把**所有假值**当成"没传"。所以 `max_steps=0` 会走默认值。
**知道这个坑存在就行**——smolagents 也是这么写的（`agents.py:480`）。正确的写法是 `max_steps if max_steps is not None else self.max_steps`。

**第 2 步：重置记忆**
```python
self.memory = self.memory.__class__(task)     # 或者直接 AgentMemory(task)
```
**直接用 `AgentMemory(task)` 就行。** 为什么必须重建：同一个 Agent 跑第二个任务时，不能带着上一次的对话历史。

**第 3 步：拿生成器**
```python
gen = self._run_stream(task, max_steps)
```

**第 4 步：分流**
```python
if stream:
    return gen                    # ★ 返回的是生成器对象，不是结果！
steps = list(gen)                 # ★ 榨干生成器
return steps[-1].model_output
```

**⚠️ `return gen` 返回的是生成器对象。** 调用方拿到后必须自己 `for` 遍历：
```python
for step in agent.run("...", stream=True):
    print(step.step_number)
```
如果调用方写 `agent.run("...", stream=True)` 而不遍历，**什么都不会发生**（生成器是惰性的，不遍历就不执行）。这是新手最常踩的坑之一。

**⚠️ `list(gen)` 为什么能"榨干"**：`list()` 会不断调 `next(gen)` 直到 `StopIteration`。生成器函数从头跑到尾。

**第 5 步：取最终答案**
```python
steps[-1].model_output
```
**为什么敢无脑取 `[-1]`**：因为 2.5.7 建立的不变量——**最后一步一定是 `is_final_answer=True`**。

但取 `[-1]` 还是有点隐晦。更自解释的写法是：
```python
final = next(s for s in reversed(steps) if s.is_final_answer)
return final.model_output
```
**这行代码正好展示了"不变量"的价值**：因为有保证，所以代码可以简单。

---

#### 2.5.9 `Agent._handle_max_steps_reached()` —— 兜底

```python
def _handle_max_steps_reached(self, step_number: int) -> ActionStep:
    """步数用完了还没答案，给个交代。"""
```

**它是什么**：Agent 的"失败优雅降级"路径。

**为什么需要它**：你原来直接 `return "模型没有找到答案"`——**这是最差的兜底**。因为此时 memory 里已经积累了一堆查询结果（第 2 拆例子里查了 5 个城市的天气），全部浪费了。

**两种实现，选一种**：

**版本 A（推荐，多花一次 API 调用）**：再调一次模型
```python
messages = self.memory.to_messages()
messages.append({"role": "user", "content": [{"type": "input_text",
    "text": "你已达到最大步数上限。请基于以上已有信息，给出你现在能给出的最佳答案。"}]})
resp = self.client.responses.create(model=self.model, input=messages, instructions=self.instructions)
return ActionStep(step_number=step_number, model_output=resp.output_text,
                  model_output_items=list(resp.output), is_final_answer=True)
```

**版本 B（省钱，不调 API）**：直接把已有的 observations 拼起来
```python
summary = "\n".join(s.observations or "" for s in self.memory.steps)
return ActionStep(step_number=step_number,
                  model_output=f"未在限定步数内完成。已收集到的信息：\n{summary}",
                  is_final_answer=True)
```

**为什么单独一个方法，不直接写在 `_run_stream` 里**：
**兜底路径和主路径必须分开写。** 混在 while 里会让循环条件变成一锅粥（你会看到 `while not done and n <= max and not (n > max and ...)` 这种鬼东西）。

**⚠️ 注意返回的 `ActionStep` 必须 `is_final_answer=True`**——这是为了维持 2.5.7 那条不变量。

### 2.6 第 2 拆综合自测脚本

```python
if __name__ == "__main__":
    # ========== 第一部分：不花钱的测试（先让这些全过）==========
    s1 = ActionStep(step_number=1); s2 = ActionStep(step_number=2)
    s1.model_output_items.append("x")
    assert s2.model_output_items == [], "ActionStep 的默认值被共享了！"

    step = ActionStep(step_number=1)
    step.model_output_items = [{"type": "function_call", "call_id": "c1"}]
    step.tool_calls = [ToolCall(name="get_weather", arguments={}, call_id="c1", result="晴")]
    m = step.to_messages()
    assert len(m) == 2 and m[1]["call_id"] == "c1"

    class FakeAgent(Agent):
        def _step_stream(self, step):
            step.model_output = f"第{step.step_number}步"
            step.is_final_answer = step.step_number >= 2
            yield

    a = FakeAgent(tools=[], model="x", max_steps=5)
    steps = list(a._run_stream("测试", 5))
    assert len(steps) == 2 and steps[-1].is_final_answer
    print("✅ 循环骨架通过（0 次 API 调用）")

    class BoomAgent(Agent):
        def _step_stream(self, step):
            raise ValueError("炸了")
            yield

    b = BoomAgent(tools=[], model="x", max_steps=3)
    steps = list(b._run_stream("测试", 3))
    assert len(steps) == 3 and all(s.error for s in steps)
    assert steps[-1].is_final_answer
    print("✅ 异常路径通过（0 次 API 调用）")

    # ========== 第二部分：真 API 测试 ==========
    tools = [WeatherTool(), CurTimeTool(), ExchangeRateTool(), get_cur_time]
    agent = Agent(tools=tools, model="deepseek-flash", max_steps=5,
                  instructions="你可以调用工具来查询信息。")

    # 测 1：非流式
    ans = agent.run("北京现在天气怎么样")
    assert ans and isinstance(ans, str)
    print("非流式答案：", ans)

    # 测 2：流式 —— 关键是能实时看到中间步骤
    print("\n--- 流式 ---")
    for st in agent.run("查一下北京和上海的天气，还有现在几点", stream=True):
        flag = "FINAL" if st.is_final_answer else "     "
        err  = f" ERR={st.error}" if st.error else ""
        print(f"[{flag} step {st.step_number}] {st.model_output or st.observations}{err}")

    # 测 3：memory 可回放
    print("\n--- memory 回放 ---")
    print("总步数：", len(agent.memory.steps))
    print("消息条数：", len(agent.memory.to_messages()))
    for s in agent.memory.steps:
        print(f"  step {s.step_number}: tool_calls={[t.name for t in (s.tool_calls or [])]} "
              f"final={s.is_final_answer}")

    # 测 4：工具失败不崩
    @tool
    def always_fail(x: str) -> str:
        """总是失败。"""
        raise ValueError("我就是要失败")

    agent2 = Agent(tools=[always_fail], model="deepseek-flash", max_steps=3)
    r = agent2.run("请调用 always_fail")
    print("\n工具失败后：", r)
    # 期望：不抛异常；能查到 tool_calls[0].result 是 "调用失败：..."

    print("\n✅ 第 2 拆全部通过")
```

### 2.7 对照源码

打开 `agents.py:552-620`，逐行对照：

| 源码 | 对应你写的 | 说明 |
|---|---|---|
| `agents.py:557` `while not returned_final_answer and self.step_number <= max_steps` | 你的 `while step_number <= max_steps` | **它为什么用标志位而不是"没有 tool_calls 就结束"？** 因为 CodeAgent 里"给最终答案"本身就是一次工具调用 |
| `agents.py:590-592` `for output in self._step_stream(action_step): yield output` | 生成器委托 | 你可以用 `yield from` 简写 |
| `agents.py:609-611` `except AgentError as e: action_step.error = e` | 你的 `except Exception` | **注释写得很明白**：只有"模型引起的错误"才记录后继续循环。第 3 拆会修好这里 |
| `agents.py:612-615` `finally: ... yield action_step` | 你的 `finally` | 一模一样，包括那个 GeneratorExit 瑕疵 |
| `agents.py:506-511` | 你的 `if stream` | 同一循环两种消费方式 |
| `agents.py:514` `assert isinstance(steps[-1], FinalAnswerStep)` | 无 | **这就是"不变量"的显式声明** |
| `memory.py:51` `class ActionStep` | 你的 `ActionStep` | 对着看那 12 个字段 |
| `memory.py:92-150` `def to_messages` | 你的 `to_messages()` | **重点读！** |

> **读 `memory.py:51-64` 时问自己**：那 12 个字段里，有几个是你**现在**真需要的？有几个是"多模态 / 计时 / token 统计 / 代码执行"才需要的？——**这就是"泛化税"的第一次现场教学。**

### 2.8 ✅ 检验问题（第 2 拆）

1. **你的 `run(stream=True)` 和 `run(stream=False)` 走的是同一个循环吗？怎么证明？**
   （提示：在 `_run_stream` 第一行插 `print("loop entered")`，两种调用各跑一次，数打印次数）

2. **`_step_stream` 和 `_run_stream` 的职责分界线画在哪里？**
   如果你在 `_run_stream` 里写了一行"如果 observations 里有'错误'两个字就……"，这个分界线是被破坏了还是没被破坏？为什么？

3. **如果 `_step_stream` 抛了异常被 `except` 吞掉，`step.error` 会怎样影响下一轮的 `to_messages()`？**
   去 `memory.py:138-148` 看 smolagents 往错误消息里塞了什么。**它为什么要在错误后面加"take care not to repeat previous errors"这句话？**（这题考的是"错误信息也是 prompt"）

4. **你的 `to_messages()` 里，一条 `ActionStep` 会生成几条 message？分别是什么 type？**
   对照 `memory.py:92-150`——**你漏了哪个分支？**（提示：`self.error is not None` 那个分支）

5. **为什么 `to_messages()` 必须先放 `model_output_items` 再放 `function_call_output`？反过来会怎样？**
   （提示：API 的配对要求。你可以故意反过来跑一次，看报什么错——**这是理解 API 约束最快的方式**）

6. **`finally` 里 `yield action_step` 和 `try` 里已经 yield 过的东西会重复吗？外部消费时看到的是什么序列？**
   （提示：跑一次流式，把每个 yield 出来的东西的 `type()` 打出来，画成时序图）

7. **`self.step_number` 为什么是循环里的局部变量/实例属性，而不是靠 `len(memory.steps)` 算？**
   （提示：`yield` 出去之后控制权就交出去了。如果外部在中途往 memory 里加了东西呢？——这叫"不要依赖可推导的状态"）

8. **`_handle_max_steps_reached` 为什么必须返回一个 `is_final_answer=True` 的 step？**
   如果你忘了设这个标志，`run()` 会怎样？（提示：`steps[-1].model_output` 会拿到什么？）

---

## 第 3 拆｜加第二个 Agent，逼出抽象基类

### 3.1 痛点

现在你只有一个 Agent（tool-calling 风格）。**再写一个「Code-as-Action」版**——让模型不输出 JSON，而是直接写一段 Python 代码，Agent 执行它，代码里可以调用工具。

写第二遍时你会痛苦地发现：**90% 的循环代码是抄的。** 只有"怎么让模型产出行动"和"怎么执行这个行动"不一样，其余（构造 step、写 memory、错误处理、max_steps 兜底）**完全相同**。

改成 `if self.agent_type == "code"` 能不能解决？能，但你每加一种 Agent 就要回头改主循环——**这是设计在报警。**

### 3.2 拆完长什么样

```python
class MultiStepAgent(ABC):          # 基类：写死循环骨架
    def __init__(self, tools, model, max_steps=5, instructions=""): ...
    def _run_stream(self, ...):     # 循环/memory/错误分流/max_steps —— 全部在这，和现在一字不差
    @abstractmethod
    def _step_stream(self, step) -> Generator:   # ★ 只声明，不实现
        ...

class ToolCallingAgent(MultiStepAgent):
    def _step_stream(self, step): ...   # 实现：让模型输出 JSON tool_calls

class CodeAgent(MultiStepAgent):
    def _step_stream(self, step): ...   # 实现：让模型写 Python 代码 + 执行
```

**这就是「模板方法模式」**：基类定流程，子类填步骤。**你手写两遍之后的自然结论。**

### 3.3 要实现/改造的清单

| # | 名字 | 动作 | 难度 |
|---|---|---|---|
| 1 | `AgentError` / `AgentGenerationError` / `AgentToolExecutionError` | 新建 | ★ |
| 2 | `MultiStepAgent` | 从 `Agent` 改造 | ★★ |
| 3 | `MultiStepAgent._step_stream()` | 改成抽象方法 | ★★ |
| 4 | `_run_stream` / `run` / `_handle_max_steps_reached` | 搬家（不改代码） | ★ |
| 5 | `ActionStep` 加 `code_action` 字段 + 改 `to_messages()` | 扩展 | ★★★ |
| 6 | `ToolCallingAgent._step_stream()` | 把第 2 拆的搬进来 | ★ |
| 7 | `CodeAgent._step_stream()` | 新写 | ★★★★ |

**建议的执行顺序**：先做 2-4（把现有的 `Agent` 改名成 `MultiStepAgent`、加抽象方法、跑通测试确认没坏），再做 1（异常家族），再做 5，最后 6-7。

### 3.4 逐个方法的详细规格

---

#### 3.4.1 异常家族 —— 修好第 2 拆那个坑

```python
class AgentError(Exception):
    """所有 Agent 相关错误的基类。"""

class AgentGenerationError(AgentError):
    """模型调用本身失败：网络断了、API key 错了、限流了。"""

class AgentToolExecutionError(AgentError):
    """工具执行失败：参数不对、超时、工具内部报错。"""
```

**为什么要分三个而不是一个**：因为**不同的错误该有不同的处理方式**。回到 2.5.7 里那个被简化掉的 `except Exception`：

```python
try:
    for out in self._step_stream(step):
        yield out
except AgentGenerationError:
    raise                      # ★ 直接崩：重试也没用，赶紧告诉用户
except AgentError as e:
    step.error = e             # ★ 记下来继续：模型能看到，能换方式重试
```

**这一条 except 分流，就是 `agents.py:606-611` 那两行注释在说的事。**

**判断标准（记这两句话就够了）**：

> **"重试有意义吗？"** —— 有意义 → 记下来继续；没意义 → 直接崩。

**用这个标准过一遍**：
| 情况 | 重试有意义？ | 归类 |
|---|---|---|
| API key 错 | ❌ 重试 100 次还是错 | `AgentGenerationError` → 崩 |
| 网络超时 | ✅ 可能下次就好了 | 其实两可，简单版归 GenerationError |
| 模型返回了不存在的工具名 | ✅ 模型会看到错误、自己改 | `AgentToolExecutionError` → 继续 |
| 工具内部 `ValueError` | ✅ 同上 | `AgentToolExecutionError` → 继续 |
| 代码里有语法错误（CodeAgent） | ✅ 模型会看到报错、改代码 | `AgentToolExecutionError` → 继续 |

**实现要求**：`_step_stream` 里要在合适的地方 `raise` 这三种异常。最简单的做法：
- 第 3 步调模型那里包 `try/except` → 转成 `AgentGenerationError`
- 第 7 步执行工具那里 `except Exception as e` → 转成 `AgentToolExecutionError`... 

**但等一下**——2.5.6 里我们让工具异常直接变成 `tc.result = f"调用失败：..."` 字符串了，没往外抛。**哪种更好？**

这是个真正值得你思考的设计题：
- **方案 A（第 2 拆的做法）**：工具异常 → 变成 result 字符串 → 模型自然看到
- **方案 B**：工具异常 → 抛 `AgentToolExecutionError` → 被 `_run_stream` 捕获 → `step.error` → 通过 `to_messages()` 的 error 分支给模型

两者的区别在于**"错误信息长什么样、走哪条路"**。B 的好处是错误在 step 层面集中处理、有统一的文案（`memory.py:138-148` 那段精心写的提示）；A 的好处是多个工具时**只有失败的那个**不影响其他工具。

**留给你判断，两种都行，但你要能说出为什么选它。**

---

#### 3.4.2 `MultiStepAgent.__init__`

就是把第 2 拆的 `Agent.__init__` 改个类名：

```python
class MultiStepAgent(ABC):
    def __init__(self, tools: list[Tool], model: str,
                 max_steps: int = 5, instructions: str = ""):
        self.tools = tools
        self.tools_by_name = {t.name: t for t in tools}
        self.tools_schema = [t.to_schema() for t in tools]
        self.model = model
        self.max_steps = max_steps
        self.instructions = instructions
        self.client = OpenAI(...)
        self.memory = AgentMemory("")
```

**判断哪些东西该放基类的标准**：

> **"这段代码，两个子类会一字不差地各写一遍吗？"** 会 → 提到基类。

用这个标准过一遍：
| 成员 | 两个子类都要吗 | 放哪 |
|---|---|---|
| `tools` / `tools_by_name` | ✅ 都要 | 基类 |
| `tools_schema` | ❌ **只有 ToolCallingAgent 要**（CodeAgent 不传 tools 参数给 API，它把工具写成 Python 函数说明） | 子类 |
| `model` / `max_steps` / `client` | ✅ 都要 | 基类 |
| `instructions` | ✅ 都要（但**值不同**，由子类传） | 基类（存）；子类（给值） |
| `memory` | ✅ 都要 | 基类 |

**这就是为什么 `__init__` 要在基类**：大部分成员是共用的。而 `tools_schema` 这种只有一半子类要的，**要么放子类的 `__init__` 里算，要么在基类算好但只让子类用**——简单版就在基类算，反正成本很低（**知道这是个妥协就行**）。

---

#### 3.4.3 `MultiStepAgent._step_stream()` —— 抽象方法

```python
@abstractmethod
def _step_stream(self, step: ActionStep) -> Generator:
    """执行一步。子类必须实现。

    契约（子类必须遵守）：
      1. 从 self.memory.to_messages() 拿历史（只读）
      2. 调模型
      3. 把工具执行结果写进 step.tool_calls[i].result 或 step.observations
      4. 如果这步产生了最终答案，把 step.is_final_answer 设为 True
      5. 可以 yield 中间产物给外部看
      6. 绝对不许 append 到 self.memory（那是基类的事）
    """
    ...
```

**它是什么**：一个**只有契约、没有实现**的方法。

**为什么要写这么详细的 docstring**：因为这是基类和子类之间的**接口约定**。基类不知道子类怎么干活，但必须规定它交付什么。**契约写得越清楚，子类越不容易写错。**

**一个值得做的实验（强烈推荐）**：

1. 先**去掉** `@abstractmethod`，把 `_step_stream` 写成一个空实现（`...`）
2. 试着 `MultiStepAgent(tools=[], model="x")` 并调用 `run()`
   → **能实例化！** 但调用时会因为 `_step_stream` 返回 `None` 不是生成器而报错，**报错信息会很难懂**
3. 再加回 `@abstractmethod`
4. 试着 `MultiStepAgent(...)` → **当场报 `TypeError: Can't instantiate abstract class ... with abstract method _step_stream`**

**这个对比实验能让你瞬间理解 ABC 在干嘛**：它把"你忘了实现某个方法"这个错误，从"运行时莫名其妙的报错"提前到了"实例化时明确的报错"。**和 1.5.1 里 `name: str` 不赋值是同一个思想：让错误尽早、明确地暴露。**

---

#### 3.4.4 `_run_stream` / `run` / `_handle_max_steps_reached` 搬家

**直接从 `Agent` 剪切粘贴到 `MultiStepAgent`，一行都不改。**

**⚠️ 如果你发现需要改动，说明你的职责划分有问题**——`_run_stream` 里混进了业务逻辑。回到 2.5.7 检查。

**唯一的改动**是 `except Exception` 换成 3.4.1 的异常分流。

**搬完立刻跑第 2 拆的自测脚本**（把 `Agent` 改名成 `MultiStepAgent`，`FakeAgent` 继承它），确认没坏。**这是"重构"的正确姿势：搬完先验证行为没变，再往上加新东西。**

---

#### 3.4.5 `ActionStep` 扩展 —— 加 `code_action`

```python
@dataclass
class ActionStep:
    step_number: int
    ...
    code_action: str | None = None      # ★ 新增：CodeAgent 走的代码
```

**为什么一个 `ActionStep` 要同时服务两种 Agent**：
因为基类的 `_run_stream` 只认 `ActionStep`，它不该知道"这一步是 tool-calling 还是 code"。**两种行动方式都往同一个容器里塞，靠"哪个字段非 None"来区分。**

**这正是 `memory.py:51-64` 里为什么同时有 `tool_calls` 和 `code_action` 两个字段的答案。** 你之前读到那个字段时的困惑，现在有答案了。

**`to_messages()` 要跟着改**：

```python
def to_messages(self) -> list[dict]:
    messages = list(self.model_output_items)

    if self.code_action is not None:
        # CodeAgent 风格：回填的是"代码执行结果"
        messages.append({
            "role": "user",
            "content": [{"type": "input_text",
                         "text": f"执行结果：\n{self.observations}"}],
        })
    else:
        # ToolCallingAgent 风格：回填的是 function_call_output
        for tc in (self.tool_calls or []):
            messages.append({
                "type": "function_call_output",
                "call_id": tc.call_id,
                "output": tc.result if tc.result is not None else "（未执行）",
            })

    return messages
```

**⚠️ 注意 CodeAgent 的回填方式完全不同**：tool-calling 用结构化的 `function_call_output`（靠 `call_id` 配对），code 用一条普通 user 消息（因为**根本没有 call_id**——模型写的是代码，不是工具调用请求）。

**这是两个子类真正不同的地方之一**，也是为什么 `to_messages` 必须分支。

---

#### 3.4.6 `ToolCallingAgent._step_stream()`

**把第 2 拆写的 `_step_stream` 原样搬进来，一行不改。**

搬完**检查一遍**：它有没有碰 `self.memory`？（只读 `to_messages()` 可以，append 不行。）

---

#### 3.4.7 `CodeAgent._step_stream()` —— 本拆最需要动脑的

```python
def _step_stream(self, step: ActionStep) -> Generator:
```

**它和 ToolCallingAgent 版本的三处不同**：

**不同点 1：instructions 完全不同**

ToolCallingAgent 的 system prompt 是"你可以调用工具"，CodeAgent 的要告诉模型"你写 Python 代码"。大概这样：

```python
instructions = f"""你可以通过编写 Python 代码来解决问题。
你可以在代码里直接调用以下函数：
{chr(10).join(f"- {t.name}({', '.join(t.inputs)}) -> {t.description}" for t in self.tools)}
请把代码放在 ```python ... ``` 代码块里。
当你得到最终答案时，调用 final_answer(答案)。
"""
```

**注意这里把工具"翻译成了 Python 函数说明"而不是 JSON Schema。** 这就是 Code-as-Action 的核心思想：**Python 的语法本身就是最好的工具描述**——模型天生会用 Python 写循环、条件、变量，而 JSON 工具调用做不到这些。

**不同点 2：调模型时不传 `tools` 参数**

```python
resp = self.client.responses.create(
    model=self.model,
    input=input_messages,
    instructions=self.instructions,      # ← 没有 tools= 了！
)
```

**不同点 3：没有 `tool_calls`，改成解析代码 + 执行**

**第 a 步：正则抠代码块**
```python
m = re.search(r"```python\n(.*?)```", step.model_output or "", re.S)
code = m.group(1) if m else ""
step.code_action = code
```
`re.S` 让 `.` 能匹配换行符（不然多行代码匹配不到）。**抠不到代码块怎么办**——简单版返回一句 `"没有找到代码块"` 作为 observation，让模型下轮重试。

**第 b 步：准备执行环境**
```python
result_box = {}

def final_answer(value):
    result_box["value"] = value

namespace = {t.name: t for t in self.tools}   # 把工具注入成可直接调用的名字
namespace["final_answer"] = final_answer
```
`namespace` 就是 `exec` 时那个"全局变量空间"。**模型写的代码里写 `get_weather(city="北京")`，找的就是这个 namespace 里的 `get_weather`。**

**第 c 步：执行**
```python
try:
    exec(code, namespace)
    if "value" in result_box:
        step.is_final_answer = True
        step.model_output = str(result_box["value"])
        step.observations = step.model_output
    else:
        step.observations = "（代码执行完毕，但没有调用 final_answer）"
except Exception as e:
    step.observations = f"代码执行出错：{type(e).__name__}: {e}"
```

**⚠️ `final_answer` 这个函数是关键设计**：它是模型和 Agent 之间的"我完事了"信号。模型不调用它，Agent 就认为这步只是中间步骤，继续循环。

**这个设计正对应 smolagents 的 `FinalAnswerTool`**（在 `default_tools.py` 里）。你去看看那个工具——**它没有任何实际逻辑，唯一的"作用"就是让模型有个东西可调，用来标记"我给答案了"。** 当时你可能觉得莫名其妙，现在你知道为什么了。

**⚠️⚠️ `exec()` 安全警告（这段一定要看）**

`exec(code)` 会执行**任意代码**。模型如果写：

```python
import os; os.system("rm -rf /")
```

你的电脑就完了。

**玩具版只在你自己的机器上、只对可信模型、只在你盯着的情况下跑。**

**那生产环境怎么办**——这就是 `local_python_executor.py` 那 **1768 行的存在理由**：
- 不用 `exec()`，而是用 `ast` 模块**逐节点解释执行**
- 遇到 `import` 语句 → 拒绝
- 遇到 `open()` / `eval()` / `__import__` 等危险函数 → 拒绝
- 限制循环次数、限制执行时间、限制内存

**你之前读到 1768 行觉得"这是什么天书"——现在你知道它为什么这么长了：它把"能执行 Python"和"不能干坏事"这两个互相矛盾的需求，硬生生用 1768 行调和出来。** 这是 C 类泛化税里最贵的一笔。

**第 d 步：yield**
```python
yield step.observations      # 把执行结果吐出去
```
注意 CodeAgent 没有 `ToolCall` 可以 yield，所以 yield 字符串就行。

### 3.5 第 3 拆综合自测脚本

```python
if __name__ == "__main__":
    # ========== 第一部分：不花钱 ==========
    try:
        MultiStepAgent(tools=[], model="x")
        raise SystemExit("❌ 抽象基类不该能实例化")
    except TypeError as e:
        print("✅ 抽象基类拦住了：", str(e)[:80])

    # to_messages 的两个分支
    s_code = ActionStep(step_number=1, model_output_items=[{"type": "message"}],
                        code_action="final_answer(1)", observations="1")
    assert len(s_code.to_messages()) == 2
    assert s_code.to_messages()[1]["role"] == "user"        # ★ code 走 user 消息

    s_tool = ActionStep(step_number=1, model_output_items=[{"type": "message"}],
                        tool_calls=[ToolCall(name="f", arguments={}, call_id="c", result="r")])
    assert s_tool.to_messages()[1]["type"] == "function_call_output"   # ★ tool 走结构化

    print("✅ to_messages 双分支通过")

    # ========== 第二部分：真 API ==========
    tools = [WeatherTool(), CurTimeTool()]

    a = ToolCallingAgent(tools=tools, model="deepseek-flash", max_steps=4)
    b = CodeAgent(tools=tools, model="deepseek-flash", max_steps=4)

    ra = a.run("北京现在天气怎么样")
    rb = b.run("北京现在天气怎么样")
    print("\nToolCallingAgent →", ra)
    print("CodeAgent        →", rb)

    # ★ 关键对比：两者的 memory.steps 都是 ActionStep 列表，结构一样
    print("\n--- 结构对比 ---")
    for name, ag in [("tool-calling", a), ("code", b)]:
        for s in ag.memory.steps:
            print(f"[{name}] step {s.step_number}: "
                  f"tool_calls={[t.name for t in (s.tool_calls or [])]} "
                  f"code_action={(s.code_action or '')[:40]!r} "
                  f"final={s.is_final_answer}")
        print(f"[{name}] 总步数={len(ag.memory.steps)}")

    print("\n✅ 第 3 拆全部通过")
```

**跑完请仔细观察**：第 3 步的循环结构、异常处理、memory 管理**完全来自基类**，两个子类只贡献了 `_step_stream` 那几十行。**这就是抽象的收益。**

### 3.6 对照源码

| 位置 | 看什么 |
|---|---|
| `agents.py:275` `class MultiStepAgent(ABC)` | 基类 `__init__` 在 `303` |
| `agents.py:761` `@abstractmethod` | 抽象方法只有签名 |
| `agents.py:1271` `class ToolCallingAgent` | 子类一，`_step_stream` 在 `1334` |
| `agents.py:1570` `class CodeAgent` | 子类二，`_step_stream` 在 `1705` |
| **`agents.py:1334` vs `agents.py:1705`** | **★ 本拆最关键**：同一个抽象方法的两份实现，对照着读，找共同前奏 |
| `agents.py:502-504` `getattr(self, "python_executor", None)` | 基类在试探"子类有没有这东西"——**抽象没做干净的症状** |
| `default_tools.py` 的 `FinalAnswerTool` | 你写的 `final_answer()` 的官方版 |

读 `1334` 和 `1705` 时注意前 15 行：两边都在做"把 memory 渲染成 messages → 记进 `step.model_input_messages` → 调模型 → 记 `step.model_output`"。**这段代码在两边几乎逐字重复。**

### 3.7 ✅ 检验问题（第 3 拆）

1. **做 3.4.3 那个实验**（先去掉 `@abstractmethod` 实例化，再加回来）。两次的报错信息分别是什么？**ABC 帮你把错误从什么时候提前到了什么时候？**

2. **`ToolCallingAgent._step_stream` 和 `CodeAgent._step_stream` 的前 15 行有什么共同点？你能把这部分提到基类吗？**
   （对照 `agents.py:1345-1350` 和 `1705` 之后。**如果 smolagents 没提取，猜猜为什么**——这题没有标准答案，考的是你敢不敢质疑框架的设计。提示：提取后基类就需要知道"怎么调模型"这个细节，而不同子类可能要调不同的 API）

3. **你的 `_run_stream` 怎么知道"这一步出最终答案了"？两种 Agent 的判断方式一样吗？**
   （提示：`step.is_final_answer` 是两个子类共同的语言——**基类靠它跟子类对话**。这就是"接口"的意义）

4. **`tools_schema` 我放在基类算了，但 `CodeAgent` 根本不用它。** 这个妥协有什么代价？如果 Agent 有 50 个工具，代价会变大吗？

5. **如果现在要加第三种 Agent（比如"让模型输出 SQL"），你需要改几个文件、动基类吗？**
   **这是你判断"抽象抽对没抽对"的唯一标准。** 如果只需要新写一个 `SQLAgent` + 一个 `_step_stream`，一行基类都不用改——抽象就是对的。

6. **`ActionStep` 为什么要同时有 `tool_calls` 和 `code_action` 两个字段？** 如果在第 2 拆你就预见到了这一点，你会怎么设计？

7. **`getattr(self, "python_executor", None)` 这个写法好不好？如果让你重构，你会怎么做？**
   （提示：可以在基类定义一个空的 `send_tools_to_executor()`，子类按需覆写——这叫"钩子方法"。**smolagents 为什么没这么做？**）

8. **`exec()` 那 1768 行的 `local_python_executor.py`，现在你知道它为什么存在了吗？** 用一句话说明它解决的核心矛盾。

---

## 第 4 拆（选做，1 小时）｜泛化税分类：学会跳过 60% 的代码

这一拆不写代码，只做一件事：**训练你"识别噪音"的能力。**

打开 `agents.py:446-620`，给每个参数和分支贴标签：

| 代码 | 为谁服务 | 类别 | 现在要不要懂 |
|---|---|---|---|
| `stream: bool` | 流式 UI | C 泛化税 | 概念懂即可 |
| `reset: bool` | 多轮对话复用 Agent | C | 跳过 |
| `images` | 多模态输入 | C | 跳过 |
| `additional_args` | 用户塞任意变量 | C | 跳过 |
| `return_full_result` | 可观测性（**阶段 6**） | C | 阶段 6 再回来 |
| `interrupt_switch` | 用户中断 | C | 跳过 |
| `planning_interval` | 定时规划（**阶段 3 设计模式**） | C | 阶段 3 再回来 |
| `managed_agents` | 多 Agent 协作（**阶段 4**） | C | 阶段 4 再回来 |
| `python_executor.send_*` | 代码沙箱（CodeAgent 专属） | C | 跳过 |
| `@abstractmethod _step_stream` | 两种 Agent | **B 设计模式** | ✅ **必须懂** |
| `except AgentGenerationError: raise` vs `except AgentError: 继续` | 错误分流策略 | **B** | ✅ **必须懂** |
| `try / except / finally` | — | A 语法 | ✅ 懂 |
| `yield` / `list()` | — | A 语法 | ✅ 懂 |
| `@dataclass` 构造 `ActionStep` | — | A 语法 | ✅ 懂 |

### ✅ 检验问题（第 4 拆）

1. **`run()` 的 7 个参数里，有几个是 C 类？**（`agents.py:446-455`）

2. **假设把所有 C 类分支全部删掉，`run()` 还剩几行？那几行的逻辑，和你写的 `run()` 差在哪里？**
   （如果答案是"基本一样"——恭喜，你已经读懂了。**这就是本拆的全部意义。**）

3. **`planning_interval` 和 `managed_agents` 分别对应你路线图的哪个阶段？**
   （阶段 3 / 阶段 4。**这就是"什么时候该回来重读"的答案**）

4. **`local_python_executor.py` 那 1768 行属于哪一类？为什么现在跳过是正确决定？**

---

## 附录 A｜语法速查（卡住时翻这里）

| 语法 | 一句话 | 在 smolagents 里 |
|---|---|---|
| **生成器 / `yield`** | 函数执行到 `yield` 就**暂停并交出一个值**，下次 `next()` 从暂停处继续。函数体里有 `yield` 就叫生成器函数，调用它不执行代码，只返回生成器 | `_run_stream` |
| **`return` 在生成器里** | 不是返回值，是抛 `StopIteration`。**最常见的坑** | — |
| **`yield from gen`** | 生成器委托，等价于 `for x in gen: yield x` | `agents.py:590` |
| **`X \| None`** | 就是 `Optional[X]`，Python 3.10+ 写法 | 到处都是 |
| **`list["Foo"]`** | 字符串是"前向引用"，因为 `Foo` 此刻可能还没定义 | `list["PIL.Image.Image"]` |
| **`@dataclass`** | 自动生成 `__init__`，按字段顺序/关键字构造 | `ActionStep` |
| **`field(default_factory=list)`** | dataclass 里可变默认值的正确写法 | ★ 见 2.5.2 |
| **`@abstractmethod` + `ABC`** | 声明"子类必须实现"，基类不能直接实例化 | `_step_stream` |
| **装饰器 `@tool`** | `@tool` 等价于 `f = tool(f)`。能让函数"变成别的东西" | `tools.py:1061` |
| **`inspect.signature()`** | 运行时读取函数的参数名/类型注解/默认值 | `@tool` |
| **`param.annotation is inspect.Parameter.empty`** | 判断"没写类型注解"。**用 `is` 不用 `==`** | `@tool` |
| **`__init_subclass__`** | 子类被定义时自动触发的钩子，用于校验 | `tools.py:140` |
| **`__call__`** | 让对象能像函数一样被调用 | `Tool.__call__` |
| **`getattr(obj, "x", None)`** | 安全取属性，没有就返回默认值 | `agents.py:502` |
| **`{**a, **b}`** | 字典解包合并 | `agents.py:504` |
| **`a or b`** | `a` 为假值时取 `b`。**注意 `0`、`""`、`[]` 也是假值** | `agents.py:480` |
| **`exec(code, ns)`** | 在命名空间 `ns` 里执行代码。**不安全** | 你的 CodeAgent |
| **元编程（`__signature__`）** | 运行时改写函数的签名信息 | `tools.py:1106` |

## 附录 B｜查源码的正确姿势

**1. 别从头读。带着问题 grep。**
```
想知道 max_steps 用完会怎样 → grep -n "max_steps" agents.py → 找到 _handle_max_steps_reached → 读那 20 行 → 完事
```

**2. 读 `tests/` 比读源码快 10 倍。**
想知道 `Tool` 怎么用？别翻文档，直接看 `tests/` 里的测试文件——**测试里的调用示例是最小可运行的，而且必须能跑通（不会过时）。**

**3. 跑起来 + 断点，比干读快 10 倍。**
```bash
pip install -e .
# VS Code 里对 examples/multiple_tools.py 打断点，F11 单步进源码
```
**你在第 2 拆写的 `_run_stream` 就是断点的最佳落点**——你会发现调用栈里的每一步你都认识。

**4. VS Code 快捷键**：`Ctrl+点击` 跳定义、`Ctrl+Shift+F` 全局搜、`Alt+←` 返回。

**5. 官方文档有中文版**：`docs/source/zh/`。

## 附录 C｜总验收

做完三拆后，用这三个问题给自己打分。**答得出来，阶段 1 才算真毕业。**

1. **我的循环和 smolagents 的循环，步骤对象里各存了什么？差在哪、为什么？**

2. **为什么它要把循环写成生成器，而不是直接 for 循环 return？**
   （提示：`agents.py:506-511`）

3. **为什么 `_step_stream` 要被抽成抽象方法，而不是写成 `if agent_type == "code"`？**

### 一张总对照表

| 你写的 | smolagents | 状态 |
|---|---|---|
| `create_schema()` | `_function_type_hints_utils.get_json_schema()` | ✅ 认识 |
| `Tool` 基类 | `tools.py:106 Tool` | ✅ 认识 |
| `@tool` 装饰器 | `tools.py:1061 tool()` | ✅ 认识 |
| `ActionStep` | `memory.py:51 ActionStep` | ✅ 认识（字段更多但同类） |
| `AgentMemory.to_messages()` | `memory.py:92 to_messages()` | ✅ 认识 |
| `MultiStepAgent` | `agents.py:275 MultiStepAgent(ABC)` | ✅ 认识 |
| `_step_stream` | `agents.py:761 @abstractmethod` | ✅ 认识 |
| `_run_stream` | `agents.py:552 _run_stream` | ✅ 认识 |
| `run(stream=)` | `agents.py:446 run` | ✅ 认识 |
| `final_answer()` | `default_tools.py` 的 `FinalAnswerTool` | ✅ 认识 |
| `AgentError` 家族 | `utils.py` 的异常类 | ✅ 认识 |
| 剩下看不懂的 | 泛化税（多模态/沙箱/规划/多 Agent/可观测性） | ⏭️ **理直气壮跳过** |

### 最后

**这份文档的目标不是让你"读懂 smolagents"，而是让你在阶段 3/4 打开 LangGraph 时，不再有"这是天书"的恐惧。**

到那时你会发现：LangGraph 比 smolagents 复杂十倍，但**复杂的部分依然是同一批东西**——状态（这边叫 memory，那边叫 State）、步骤（这边 `_step_stream`，那边是节点）、循环（这边 while，那边是图的边）、错误处理与重试。**你已经在自己手里造过一遍这些东西的雏形了。**

---

*写于 2026-09-21，基于 smolagents v1.27.0.dev0。行号会漂，抽象不会。*
