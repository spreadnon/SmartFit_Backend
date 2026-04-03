from typing import Annotated, TypedDict, List
import operator
import json
import requests
import os
import uuid # Generate unique IDs for tool calls
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, ToolCall
from langgraph.graph import StateGraph, END
from fastapi import HTTPException # Used for error handling in llm_node

# 从.env文件加载环境变量
load_dotenv()
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# ===================== 1. 定义全局状态（核心！）=====================
# AgentState 定义了在 LangGraph 工作流中节点之间传递的状态。
# 它是一个 TypedDict，允许类型提示和清晰的结构。
class AgentState(TypedDict):
    # messages: 消息列表。每个节点都可以向此列表追加消息。
    # Annotated[List[dict], operator.add] 意味着当为 'messages' 分配新值时，
    # 它应该被添加到现有列表中（连接）。
    messages: Annotated[List[dict], operator.add]
    # tool_calls: LLM 决定执行的工具调用列表。
    # 如果此列表不为空，则表示需要执行工具。
    tool_calls: List[dict]

# ===================== 2. 定义工具 =====================
# 这些是我们的 Agent 可以“调用”或“使用”来执行操作的函数。
# @tool 装饰器来自 langchain_core.tools，使它们可被 LLM 发现。

@tool
def search(query: str) -> str:
    """
    执行给定查询的网络搜索。
    这是实际网络搜索功能的占位符。
    """
    return f"【搜索结果】关于 {query}：LangGraph 是 LangChain 官方工作流引擎，用于构建循环、多智能体、状态化 Agent。"

@tool
def calculate(expression: str) -> str:
    """
    评估一个简单的数学表达式。
    处理基本的算术运算。
    """
    try:
        return str(eval(expression))
    except Exception:
        return "计算错误"

# 所有可用工具的列表
tools = [search, calculate]
# 创建一个将工具名称映射到其函数的字典，以便于查找
tool_map = {t.name: t for t in tools}

# 以与 Qwen API 兼容的格式定义工具的 schema。
# 这会告诉 Qwen 它可以调用的函数及其参数。
qwen_tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "联网搜索信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "简单计算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

# ===================== 3. LLM 节点：思考 + 工具决策 =====================
# 此节点负责与 Qwen LLM 交互。
# 它接收当前状态，向 Qwen 发送消息，并处理 Qwen 的响应。
def llm_node(state: AgentState):
    # 将 LangChain 消息对象转换为适合 Qwen API 的格式。
    # Qwen API 期望一个包含“role”和“content”的字典列表。
    # 如果存在工具调用，它们将嵌入到助手消息中。
    messages_for_qwen = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            messages_for_qwen.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                # 如果 AI 消息包含工具调用，则将其格式化为 Qwen。
                # 对于 Qwen，如果存在工具调用，则内容字段应省略，并使用 'function_call' 结构。
                # Qwen API 期望单个 function_call，而不是列表。
                if len(msg.tool_calls) > 1:
                    print("警告：Qwen API可能不支持单个消息中的多个工具调用。将只使用第一个工具调用。")
                
                first_tool_call = msg.tool_calls[0]
                function_call_content = {
                    "name": first_tool_call["name"],
                    "arguments": json.dumps(first_tool_call["args"]) # 参数必须是 JSON 字符串
                }
                messages_for_qwen.append({"role": "assistant", "function_call": function_call_content})
            else:
                messages_for_qwen.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            # 工具消息包含工具执行的结果。
            # 对于 Qwen，工具结果应以 'function' 角色发送，包含函数名称和内容。
            messages_for_qwen.append({"role": "function", "name": msg.name, "content": msg.content})

    # 为 Qwen API 请求设置 HTTP 标头。
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {QWEN_API_KEY}" # 使用从 .env 加载的 API 密钥
    }

    # 构造 Qwen API 请求的有效负载。
    payload = {
        "model": "qwen-max", # 指定要使用的 Qwen 模型
        "input": {
            "messages": messages_for_qwen # 对话历史
        },
        "parameters": {
            "result_format": "message", # 请求消息样式输出
            "tools": qwen_tools_schema # 提供工具定义
        }
    }

    try:
        # 向 Qwen API 发送 POST 请求。
        response = requests.post(QWEN_API_URL, headers=headers, json=payload)
        response.raise_for_status() # 对于 HTTP 错误（4xx 或 5xx）引发异常
        response_data = response.json() # 解析 JSON 响应

        # 从 Qwen 的响应中提取消息。
        qwen_message = response_data["output"]["choices"][0]["message"]
        
        content = qwen_message.get("content", "") # Qwen可能在有工具调用时没有content
        tool_calls_for_agent_state = []
        langchain_tool_calls = []

        if "tool_calls" in qwen_message:
            for tc in qwen_message["tool_calls"]:
                function_name = tc["function"]["name"]
                function_args = json.loads(tc["function"]["arguments"])
                tool_call_id = tc["id"]
                
                # 为 AgentState
                tool_calls_for_agent_state.append({
                    "name": function_name,
                    "args": function_args,
                    "id": tool_call_id
                })
                # 为 AIMessage
                langchain_tool_calls.append(ToolCall(name=function_name, args=function_args, id=tool_call_id))

        # 从 Qwen 的响应创建 AIMessage 对象。
        ai_message = AIMessage(content=content, tool_calls=langchain_tool_calls)

        # 返回更新后的状态。
        return {
            "messages": [ai_message], # 追加 AI 的响应消息
            "tool_calls": tool_calls_for_agent_state # 追加 AI 进行的任何工具调用
        }

    except requests.exceptions.RequestException as e:
        # 处理网络或 HTTP 请求错误。
        raise HTTPException(status_code=500, detail=f"Qwen API 请求失败: {e}")
    except KeyError as e:
        # 如果 Qwen API 响应结构不符合预期，则处理错误。
        raise HTTPException(status_code=500, detail=f"Qwen API 响应解析错误: 缺少键 {e}。响应: {response_data}")

# ===================== 4. 工具执行节点 =====================
# 此节点执行 LLM 决定调用的工具。
def tool_node(state: AgentState):
    results = []
    # 遍历 LLM 请求的每个工具调用。
    for call in state["tool_calls"]:
        # 使用工具名称查找实际的工具函数。
        tool_function = tool_map[call["name"]]
        # 使用提供的参数调用工具。
        res = tool_function.invoke(call["args"])
        # 将结果作为 ToolMessage 追加到消息列表中，包含 tool_call_id。
        results.append(ToolMessage(content=res, name=call["name"], tool_call_id=call["id"]))
    # 返回包含工具执行结果的更新状态。
    return {"messages": results}

# ===================== 5. 条件边：继续或结束 =====================
# 此函数根据当前状态确定工作流中的下一个节点。
def should_continue(state: AgentState):
    # 从对话历史中获取最后一条消息。
    last_message = state["messages"][-1]
    # 如果最后一条消息是 AIMessage 并且包含工具调用，
    # 则表示 LLM 想要使用工具，因此我们路由到“tool”节点。
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool"  # 路由到工具执行节点
    # 否则，如果没有工具调用，对话可以结束。
    return END         # 结束工作流

# ===================== 6. 构建 LangGraph 工作流 =====================
# 使用我们定义的 AgentState 初始化 StateGraph。
workflow = StateGraph(AgentState)

# 将节点添加到工作流。每个节点对应一个函数。
workflow.add_node("llm", llm_node)   # LLM 交互节点
workflow.add_node("tool", tool_node) # 工具执行节点

# 设置工作流的入口点。第一个要执行的节点。
workflow.set_entry_point("llm")

# 添加条件边。从“llm”节点开始，下一步取决于 `should_continue`。
# 如果 `should_continue` 返回“tool”，则转到“tool”节点。
# 如果 `should_continue` 返回 END，则工作流终止。
workflow.add_conditional_edges(
    "llm",
    should_continue
)

# 添加常规边。在“tool”节点执行后，它总是返回到“llm”节点。
# 这会创建一个循环，允许 LLM 处理工具结果并决定下一步。
workflow.add_edge("tool", "llm")

# 将工作流编译为可执行应用程序。
agent = workflow.compile()

# ===================== 测试运行 =====================
if __name__ == "__main__":
    # 需要搜索和计算的示例问题。
    question = "帮我规划一下周五的健康饮食"
    
    # 使用初始 HumanMessage 调用 Agent。
    # `tool_calls` 列表最初为空。
    res = agent.invoke({
        "messages": [HumanMessage(content=question)],
        "tool_calls": []
    })

    # 打印 Agent 的最终答案。
    # `messages` 列表中的最后一条消息将是最终的 AIMessage。
    print("===== 最终回答 =====")
    print(res["messages"][-1].content)
