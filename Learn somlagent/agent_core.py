from dataclasses import dataclass, field
from tool_base import *
from openai import OpenAI
from openai.types.responses import Response
from typing import Generator
import os
import json

@dataclass
class ToolCall:
	name : str
	arguments : dict
	call_id : str
	result : str | None = None

@dataclass
class ActionStep:
	'''
	存Agent每一步的全部信息

	step_number --存储现在是第几步
	model_output_items --模型返回的原始信息
	model_output --模型输出的纯文本
	tool_calls --模型想调用的工具及工具返回的结果
	observations --模型调用工具后返回结果拼接成的摘要
	error --记录是否报错
	is_final_answer --是否为最终答案
	model_input_messages --模型该步看到的输入(debug)
	'''
	step_number : int
	model_output_items : list = field(default_factory=list)
	model_output : str | None = None
	tool_calls : list[ToolCall] | None = None
	observations : str | None = None
	error : Exception | None = None
	is_final_answer : bool = False
	model_input_messages : list[dict] | None = None

	def to_messages(self) -> list[dict]:
		'''返回需要追加到历史中的所有信息'''
		message = []
		message.extend(self.model_output_items)

		for tc in (self.tool_calls or []) :
			message.append({
				"type" : "function_call_output",
				"call_id" : tc.call_id,
				"output" : tc.result if tc.result is not None else "（未执行）",
			})
		return message

class AgentMemory:
	def __init__(self, task : str):
		self.task = task
		self.steps : list[ActionStep] = []		

	def reset(self):
		self.steps = []

	def append(self, step : ActionStep):
		self.steps.append(step)

	def to_messages(self) -> list[dict]:
		messages : list[dict] = [{
			"role" : "user",
			"content" : [{
				"type" : "input_text",
				"text" : self.task,
			}],
		}] 

		for step in self.steps:
			messages.extend(step.to_messages())
		
		return messages

class Agent:
	def __init__(self, tools : list[Tool], model : str, max_steps : int = 5,
				instructions : str = "", api_key : str | None = None):
		self.tools = tools
		self.tools_by_name = {t.name : t for t in self.tools}
		self.tools_schema = [t.to_schema() for t in self.tools]
		self.model = model
		self.max_steps = max_steps
		self.instructions = instructions
		api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
		if not api_key:
			raise RuntimeError("未找到 DEEPSEEK_API_KEY：请设置环境变量，或给 Agent(api_key=...) 传一个。")
		self.client = OpenAI(api_key = api_key, base_url = "https://api.deepseek.com")
		self.memory = AgentMemory("")

	def _step_stream(self, step : ActionStep) -> Generator:
		input_messages = self.memory.to_messages()
		step.model_input_messages = input_messages

		resp : Response = self.client.responses.create(
			input = input_messages,
			model = self.model,
			instructions = self.instructions,
			tools = self.tools_schema,
		)

		step.model_output_items = list(resp.output)
		step.model_output = resp.output_text
		step.tool_calls = [
			ToolCall(
				name = o.name,
				arguments = json.loads(o.arguments),
				call_id = o.call_id,
			)
			for o in resp.output
			if o.type == "function_call"
		]

		if not step.tool_calls:
			step.is_final_answer = True
			return

		for tc in step.tool_calls:
			try:
				tc.result = self.tools_by_name[tc.name](**tc.arguments) 
			except Exception as e:
				tc.result = f"调用失败:{type(e).__name__} : {e}"
			yield tc

		step.observations = "\n".join(
			f"{tc.name}({tc.arguments}) -> {tc.result}"
			for tc in step.tool_calls
		)

	def _run_stream(self, task, max_steps):
		step_number = 1
		while step_number <= max_steps:
			step = ActionStep(step_number=step_number)
			try:
				for out in self._step_stream(step):
					yield out
			except Exception as e:
				step.error = e
			finally:
				self.memory.append(step)
				yield step
				step_number += 1

			if step.is_final_answer:
				return

		yield self._handle_max_steps_reached(step_number)

	def _handle_max_steps_reached(self, step_number : int) -> ActionStep:
		messages = self.memory.to_messages()
		messages.append({"role": "user", "content": [{"type": "input_text",
			"text": "你已达到最大步数上限。请基于以上已有信息，给出你现在能给出的最佳答案。"}]})
		resp = self.client.responses.create(model=self.model, input=messages, instructions=self.instructions)
		return ActionStep(step_number=step_number, model_output=resp.output_text,
						model_output_items=list(resp.output), is_final_answer=True)

	def run(self, task : str, stream : bool = False, max_steps : int | None = None) -> str | Generator:
		max_steps = max_steps if max_steps is not None else self.max_steps
		self.memory = AgentMemory(task = task)
		gen = self._run_stream(max_steps = max_steps,task = task)
		if stream:
			return gen
		steps = list(gen)
		return steps[-1].model_output

if __name__ == "__main__":
	# ========== 第一部分：不花钱的测试（先让这些全过）==========
	s1 = ActionStep(step_number=1)
	s2 = ActionStep(step_number=2)
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
			return          # 立刻结束，不往流里吐 None
			yield           # 不可达，只为让这个函数变成生成器

	a = FakeAgent(tools=[], model="x", max_steps=5, api_key="sk-test")
	steps = list(a._run_stream("测试", 5))
	assert len(steps) == 2 and steps[-1].is_final_answer
	print("✅ 循环骨架通过（0 次 API 调用）")

	class BoomAgent(Agent):
		def _step_stream(self, step):
			raise ValueError("炸了")
			yield

		def _handle_max_steps_reached(self, step_number):
			# 换成假兜底，隔离真实 API，这一段才能真的 0 次调用
			return ActionStep(step_number=step_number, model_output="兜底答案",
							is_final_answer=True)

	b = BoomAgent(tools=[], model="x", max_steps=3, api_key="sk-test")
	steps = list(b._run_stream("测试", 3))
	assert len(steps) == 4                      # 3 个异常步 + 1 个兜底步
	assert all(s.error for s in steps[:-1])     # 兜底步不该带 error
	assert steps[-1].is_final_answer and steps[-1].error is None
	print("✅ 异常路径通过（0 次 API 调用）")

	# ========== 第二部分：真 API 测试 ==========
	tools = [Weather_tool(), Time_tool(), get_cur_time]
	agent = Agent(tools=tools, model="deepseek-flash", max_steps=5,
					instructions="你可以调用工具来查询信息。")

	# 测 1：非流式
	ans = agent.run("北京现在天气怎么样")
	assert ans and isinstance(ans, str)
	print("非流式答案：", ans)

	# 测 2：流式 —— 关键是能实时看到中间步骤
	print("\n--- 流式 ---")
	for st in agent.run("查一下北京和上海的天气，还有现在几点", stream=True):
		if isinstance(st, ToolCall):
			print(f"[  tool ] {st.name}({st.arguments}) -> {st.result}")
			continue
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
