from typing import Annotated, Literal, TypedDict, List, Optional, Union
import operator
import json
import requests
import os
import uuid # Generate unique IDs for tool calls
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, ToolCall
from langgraph.graph import MessagesState, StateGraph, END, add_messages
from langgraph.graph.message import AnyMessage # Import AnyMessage to fix NameError during state evaluation
from langgraph.checkpoint.memory import MemorySaver # 导入内存持久化存储
from langgraph.prebuilt import ToolNode, tools_condition
from fastapi import HTTPException # Used for error handling in llm_node
from langchain_community.chat_models import ChatTongyi 

# 从.env文件加载环境变量
load_dotenv()
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

# 再扩展自己的业务字段！
class AgentState(MessagesState):
    # 系统自带：messages: [...]
    
    # 你自己加的字段（从Apple登录传进来！）
    user_id: int          # 关键！登录用户ID
    user_phone: Optional[str]
    order_id: Optional[str]  # 订单ID（你未来订单服务可用）
    next_agent: str  # 下一个执行的智能体

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

# ===================== 【工具3】查询订单（隐私）=====================
@tool
def get_user_order(user_id: int, order_id: str):
    """查询用户的订单信息
    必须传入 user_id 和 order_id
    """
    return f"【订单信息】用户{user_id} 订单{order_id}：iPhone 16，价格5999元"


# 所有可用工具的列表
tools = [search, calculate, get_user_order]
tool_map = {t.name: t for t in tools}

llm = ChatTongyi(
    model="qwen-turbo",  # qwen-plus / qwen-max 都可以
    temperature=0,
    dashscope_api_key=QWEN_API_KEY  # 显式传递 API Key，或将环境变量名改为 DASHSCOPE_API_KEY
).bind_tools(tools)  # 关键：绑定工具，支持函数调用

# ===================== 【工人1】搜索智能体 =====================
def search_agent(state: AgentState):
    llm_with_tools = llm.bind_tools([search])
    res = llm_with_tools.invoke(state["messages"])
    return {"messages": [res]}

# ===================== 【工人2】计算智能体 =====================
def calculate_agent(state: AgentState):
    llm_with_tools = llm.bind_tools([calculate])
    res = llm_with_tools.invoke(state["messages"])
    return {"messages": [res]}

# ===================== 【工人3】订单智能体 =====================
def get_user_order_agent(state: AgentState):
    # 将 state 中的 user_id 和 order_id 注入到上下文中
    context = f"当前用户ID: {state['user_id']}, 订单ID: {state.get('order_id', '未提供')}"
    messages = [{"role": "system", "content": f"你可以直接使用以下信息：{context}"}] + state["messages"]
    
    llm_with_tools = llm.bind_tools([get_user_order])
    res = llm_with_tools.invoke(messages)
    return {"messages": [res]}

# ===================== 【主管】Supervisor（核心！）=====================
def supervisor(state: AgentState):
    # 检查最后一条消息，如果已经是一个完整的回答（没有工具调用），则应该结束。
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
        # 如果最后一条消息没有工具调用且内容不为空，说明工人已经回答了用户
        if last_message.content:
            return {"next_agent": "END"}

    system_prompt = """
    你是主管，负责任务分发。
    根据用户的最新问题和当前进度，从以下选项中选择一个最合适的处理者：
    1. search_agent: 涉及信息查询、搜索。
    2. calculate_agent: 涉及数学计算。
    3. order_agent: 涉及订单查询、购物、物流。
    4. END: 任务已完成，或者已经有结果可以反馈给用户。

    注意：
    - 必须只输出选项名称（search_agent, calculate_agent, order_agent, END）。
    - 不要输出任何解释或其他文字。
    """
    messages = [{"role": "system", "content": system_prompt}] + state["messages"]
    decision = llm.invoke(messages).content.strip()
    
    # 简单的防御性处理，防止 LLM 输出多余文字
    valid_agents = ["search_agent", "calculate_agent", "order_agent", "END"]
    # 检查输出中是否包含任何一个有效关键词
    for agent in valid_agents:
        if agent in decision:
            return {"next_agent": agent}
            
    return {"next_agent": "END"}

# ===================== 路由：决定下一个智能体 =====================
def router(state: AgentState) -> Literal["search_agent", "calculate_agent", "order_agent", "END"]:
    return state["next_agent"]
    

# 不用自己写 TypedDict！极简！
def llm_node(state: AgentState):
    # 👉 这里可以读取当前登录用户信息！
    user_id = state["user_id"]
    order_id = state["order_id"]
    
    # 构造包含上下文的系统消息，让模型知道当前的 user_id 和 order_id
    system_msg = {
        "role": "system", 
        "content": f"当前登录用户ID: {user_id}, 当前正在处理的订单ID: {order_id}。如果需要查询订单，请直接使用这些参数。"
    }
    
    messages = [system_msg] + state["messages"]
    
    response = llm.invoke(messages)
    print(f"【AI】思考中... 工具调用: {response.tool_calls}")

    return {"messages": [response]}


# ===================== 4. 工具执行节点 =====================
def tool_node(state: AgentState):
    results = []
    # 遍历 LLM 请求的每个工具调用。
    for call in state["messages"][-1].tool_calls:
        print(f"【系统】执行工具: {call['name']} 参数: {call['args']}")
        # 使用工具名称查找实际的工具函数。
        tool_function = tool_map[call["name"]]
        # 使用提供的参数调用工具。
        res = tool_function.invoke(call["args"])
        # 将结果作为 ToolMessage 追加到消息列表中，包含 tool_call_id。
        results.append(ToolMessage(content=res, name=call["name"], tool_call_id=call["id"]))
    # 返回包含工具执行结果的更新状态。
    return {"messages": results}

# ===================== 🎯 精准路由：判断是否需要中断 =====================
def tool_router(state: AgentState):
    # 取出LLM想调用的工具
    last_msg = state["messages"][-1]
    tool_calls = last_msg.tool_calls

    if not tool_calls:
        return END

    # 只看第一个工具（支持多工具也可以判断）
    tool_name = tool_calls[0]["name"]

    # 👇 核心规则：只有查询订单才中断
    if tool_name == "get_user_order":
        return "interrupt"  # 走中断
    else:
        return "tools"      # 直接执行

# ===================== 构建多智能体图 =====================
workflow = StateGraph(AgentState)

#添加3个工人+1个主管
workflow.add_node("search_agent", search_agent)
workflow.add_node("calculate_agent", calculate_agent)
workflow.add_node("order_agent", get_user_order_agent)
workflow.add_node("supervisor", supervisor)

workflow.set_entry_point("supervisor")
workflow.add_conditional_edges(
    "supervisor",
    router,
    {
        "search_agent": "search_agent",
        "calculate_agent": "calculate_agent",
        "order_agent": "order_agent",
        "END": END
    }
)

# 所有智能体执行完 → 回到主管（循环！）
workflow.add_edge("search_agent", "supervisor")
workflow.add_edge("calculate_agent", "supervisor")
workflow.add_edge("order_agent", "supervisor")

# 初始化内存存储
memory = MemorySaver()

# 编译工作流，添加中断点和持久化存储
# interrupt_after=["llm"] 表示在 llm 节点执行后中断，等待人工确认或恢复
agent = workflow.compile() #(checkpointer=memory, interrupt_after=["llm"])

# ===================== 测试运行 =====================
if __name__ == "__main__":
    # # 需要搜索和计算的示例问题。
    # question = "LangGraph是什么？再算 100+200*3"
    
    # # 定义配置，包含 thread_id 用于标识对话
    # config = {"configurable": {"thread_id": "user_123"}}

    # res = agent.invoke({
    #     "user_id": 1001,
    #     "user_phone": "13800138000",
    #     "order_id": "ORDER_20250001",
    #     "messages": [{
    #         "role": "user", 
    #         "content": "LangGraph是什么？算 100+200*3，再查我的订单"
    #     }]
    # }, config=config)

    # # 恢复执行
    # print("\n恢复执行...")
    # # 当 invoke(None) 时，它会从 checkpointer 中读取 thread_id 对应的状态继续执行
    # res = agent.invoke(None, config=config)
    
    # print("\n最终回答：")
    # print(res["messages"][-1].content)

    res = agent.invoke({
        "user_id": 1001,
        "messages": [{"role": "user", "content": "LangGraph 是什么？帮我算 123 * 456"}]
    })
    print(res["messages"][-1].content)