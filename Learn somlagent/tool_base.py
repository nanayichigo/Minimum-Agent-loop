# coding=utf-8 
from abc import ABC,abstractmethod
from pydantic import BaseModel
from typing import Any,Callable
import time
import inspect

class Tool(ABC):
	name : str
	inputs : dict[str, dict]
	description : str

	'''
	这里inputs是用于描述函数中各个元素
	inputs将原本应该传入的properties,差分成以元素为单位,并打上required标记是否必须
	后续to_schema处理成标准的JSON Schema
	inputs中元素格式如下
	"city" : {
		"type" : "string",
		"description" : "城市名",
		"required" : True,
	}
	'''

	@abstractmethod
	def forward(self, **kwargs) -> str:
		pass

	def __call__(self, **kwargs) -> str:
		return self.forward(**kwargs)

	def to_schema(self) -> dict:
		requried : list = []
		properties : dict[str, dict] = {**self.inputs}
		for key in properties:
			if properties[key].pop("required"):
				requried.append(key)
		
		return {
			"type" : "function",
			"name" : self.name,
			"description" : self.description,
			"parameters" : {
				"type" : "object",
				"properties" : properties,
				"required" : requried,
			},
		}


class Time_tool(Tool):
	def __init__(self):
		self.name = "Time_tool"
		self.description = "获取当前时间"
		self.inputs = {}

	def forward(self) -> str:
		return f"现在时间是{time.strftime("%X")}"

class Weather_tool(Tool):
	def __init__(self):
		self.name = "Weather_tool"
		self.description = "查询某城市的当前天气"
		self.inputs = {
			"city" : {
				"type" : "string",
				"description" : "城市名",
				"required" : True,
			},
		}

	def forward(self, city : str) -> str:
		return f"{city}今天天气晴朗"

_PY_TO_JSON : dict = {
	str : "string",
	int : "integer",
	bool : "boolean",
	float : "number",
	list : "Array",
	dict : "object",
}

def python_type_to_json_type(annotation) -> str:
	'''python类型向json类型转换'''
	if annotation in _PY_TO_JSON :
		return _PY_TO_JSON[annotation]

def tool(fn : Callable) -> Tool:
	'''tool装饰器,返回包装好的Tool子类'''
	class SimpleTool(Tool):
		sig = inspect.signature(fn)
		name = fn.__name__
		description = (fn.__doc__ or "").strip().split("\n")[0]
		inputs = {}
		required = []
		for pname, param in sig.parameters.items():
			if param.annotation is inspect.Parameter.empty:
				raise TypeError(f"参数 {pname} 缺少类型注解，@tool 需要它来生成 schema")
			inputs[pname] = {
				"type" : python_type_to_json_type(param.annotation),
				"description" : pname,
			}
			if param.default is inspect.Parameter.empty:
				required.append(pname)
				inputs[pname]["required"] = True
			else:
				inputs[pname]["required"] = False

		def forward(self, **kwargs) -> str:
			return fn(**kwargs)
	return SimpleTool()

@tool
def get_cur_time() -> str:
	return f"{time.strftime('%X')}"

if __name__ == "__main__":
    # --- 基类层面 ---
    try:
        Tool(); raise SystemExit("❌ Tool() 不该能实例化")
    except TypeError:
        pass

    # --- 类式工具 ---
    w = Weather_tool()
    assert w.name == "Weather_tool"
    assert w(city="北京").startswith("北京")
    s = w.to_schema()
    assert s["parameters"]["required"] == ["city"]
    assert "required" not in s["parameters"]["properties"]["city"]

    # --- 无参数工具 ---
    t = Time_tool()
    ts = t.to_schema()
    assert ts["parameters"]["properties"] == {}
    assert ts["parameters"]["required"] == []
    assert ":" in t()

    # --- 装饰器工具 ---
    assert isinstance(get_cur_time, Tool)
    assert type(get_cur_time).__name__ == "SimpleTool"
    assert get_cur_time.name == "get_cur_time"

    # --- 统一注册与调用（模拟 Agent 的行为）---
    tools = [Weather_tool(), Time_tool(), get_cur_time]
    tools_by_name = {x.name: x for x in tools}
    schemas = [x.to_schema() for x in tools]
    assert len(schemas) == 3
    assert tools_by_name["Weather_tool"](city="上海").startswith("上海")

    print("✅ 第 1 拆全部通过")
