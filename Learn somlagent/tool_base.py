# coding=utf-8 
from abc import ABC,abstractmethod
from pydantic import BaseModel
from typing import Any
import time

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

	def forward(self, city_name : str) -> str:
		return f"{city_name}今天天气晴朗"

if __name__ == "__main__":
	weather_tool = Weather_tool()
	s = Weather_tool().to_schema()
	assert s["type"] == "function"
	assert s["name"] == "Weather_tool"
	assert s["parameters"]["required"] == ["city"]
	assert s["parameters"]["properties"]["city"]["type"] == "string"
	assert "required" not in s["parameters"]["properties"]["city"] 
	assert s["parameters"]["properties"]["city"]["description"] == "城市名"
	print(weather_tool(city_name = "北京"))
