from typing import Annotated, TypedDict, List
import operator
import json
import requests
from langchain_core.tools import tool
from fastapi import HTTPException
from langgraph.graph import StateGraph, END
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, ToolCall

load_dotenv()  # 加载.env文件
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# ===================== 1. 全局状态（核心！）=====================
class AgentState(TypedDict):
    # 消息列表：所有节点都能追加
    messages: Annotated[List[dict], operator.add]
    # LLM 是否要调用工具
    tool_calls: List[dict]

# ===================== 2. 定义工具 =====================
@tool
def search(query: str) -> str:
    """联网搜索信息"""
    return f"【搜索结果】关于 {query}：LangGraph 是 LangChain 官方工作流引擎，用于构建循环、多智能体、状态化 Agent。"

@tool
def calculate(expression: str) -> str:
    """简单计算"""
    try:
        return str(eval(expression))
    except:
        return "计算错误"

# 工具列表
tools = [search, calculate]
tool_map = {t.name: t for t in tools}

qwen_tools_schema = [
    {
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
def llm_node(state: AgentState):
    messages = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                # Qwen API expects tool calls to be part of the assistant message
                tool_calls_content = []
                for tc in msg.tool_calls:
                    tool_calls_content.append({
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.args)
                        }
                    })
                messages.append({"role": "assistant", "content": msg.content, "tool_calls": tool_calls_content})
            else:
                messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            messages.append({"role": "tool", "content": msg.content, "tool_call_id": msg.tool_call_id})

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {QWEN_API_KEY}"
    }

    payload = {
        "model": "qwen-max",
        "input": {
            "messages": messages
        },
        "parameters": {
            "result_format": "message",
            "tools": qwen_tools_schema
        }
    }

    try:
        response = requests.post(QWEN_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        response_data = response.json()
        
        qwen_message = response_data["output"]["choices"][0]["message"]
        
        content = qwen_message["content"]
        tool_calls = []
        langchain_tool_calls = []

        if "tool_calls" in qwen_message:
            for tc in qwen_message["tool_calls"]:
                function_name = tc["function"]["name"]
                function_args = json.loads(tc["function"]["arguments"])
                tool_call_id = tc["id"]
                
                # For AgentState
                tool_calls.append({
                    "name": function_name,
                    "args": function_args,
                    "id": tool_call_id
                })
                # For AIMessage
                langchain_tool_calls.append(ToolCall(name=function_name, args=function_args, id=tool_call_id))

        ai_message = AIMessage(content=content, tool_calls=langchain_tool_calls)

        return {
            "messages": [ai_message],
            "tool_calls": tool_calls
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Qwen API request failed: {e}")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Qwen API response parsing error: Missing key {e}. Response: {response_data}")

    
# ===================== 4. 工具执行节点 =====================
def tool_node(state: AgentState):
    results = []
    for call in state["tool_calls"]:
        tool = tool_map[call["name"]]
        res = tool.invoke(call["args"])
        results.append({
            "role": "tool",
            "content": res,
            "tool_call_id": call["id"]
        })
    return {"messages": results}

# ===================== 5. 条件路由：继续 or 结束 =====================
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool"  # 有工具调用 → 执行工具
    return END         # 无工具 → 结束

# ===================== 6. 构建 LangGraph 流程 =====================
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("llm", llm_node)
workflow.add_node("tool", tool_node)

# 入口
workflow.set_entry_point("llm")

# 条件边：llm → tool 或 END
workflow.add_conditional_edges(
    "llm",
    should_continue
)

# 工具执行完 → 回到 LLM（形成循环！）
workflow.add_edge("tool", "llm")

# 编译成可执行 App
agent = workflow.compile()

# ===================== 测试运行 =====================
if __name__ == "__main__":
    question = "LangGraph 和 LangChain 有什么区别？然后帮我算 100+200*3"
    
    res = agent.invoke({
        "messages": [HumanMessage(content=question)],
        "tool_calls": []
    })

    # 输出最终回答
    print("===== 最终回答 =====")
    print(res["messages"][-1].content)