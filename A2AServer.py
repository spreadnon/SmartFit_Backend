from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import asyncio
import json
import uuid
import time
from datetime import datetime

app = FastAPI(title="A2A Agent Server", version="1.0")

# 内存任务队列（正式项目可换 Redis/数据库）
tasks = {}

# ------------------------------
# A2A 消息结构体定义
# ------------------------------
class AgentInfo(BaseModel):
    agent_id: str
    agent_name: Optional[str] = None

class A2AMessage(BaseModel):
    a2a_version: str = "1.0"
    message_id: str
    session_id: str
    sender: AgentInfo
    recipient: AgentInfo
    type: str  # request / response / event / error
    action: Optional[str] = None
    is_async: Optional[bool] = Field(False, alias="async")
    reply_to: Optional[str] = None
    task_id: Optional[str] = None
    status: Optional[str] = None
    payload: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None

# ------------------------------
# A2A 核心接口（统一入口）
# ------------------------------
@app.post("/a2a/v1/message")
async def a2a_message(msg: A2AMessage):
    # 只处理请求类型
    if msg.type != "request":
        return error_response(msg.message_id, "INVALID_TYPE", "仅支持 request 消息")

    # 根据 action 分发任务
    if msg.action == "query_weather":
        return handle_weather(msg)
    
    # elif msg.action == "generate_article":
    #     return handle_async_task(msg)

    # SSE 流式：AI 对话 / 文章生成
    elif msg.action == "chat_stream":
        return handle_chat_stream(msg)
    
    else:
        return error_response(msg.message_id, "ACTION_NOT_SUPPORT", f"不支持动作：{msg.action}")

# ------------------------------
# 同步接口示例：天气查询
# ------------------------------
def handle_weather(msg: A2AMessage):
    city = msg.payload.get("city", "")
    if not city:
        return error_response(msg.message_id, "MISSING_CITY", "缺少城市参数")

    return {
        "a2a_version": "1.0",
        "message_id": new_id(),
        "session_id": msg.session_id,
        "sender": {"agent_id": "backend_agent", "agent_name": "Python后端智能体"},
        "recipient": msg.sender.dict(),
        "type": "response",
        "reply_to": msg.message_id,
        "status": "success",
        "payload": {
            "city": city,
            "temperature": "18°C",
            "weather": "晴",
            "humidity": "35%"
        }
    }

# ------------------------------
# 异步任务示例：文章生成
# ------------------------------
def handle_async_task(msg: A2AMessage):
    task_id = f"task_{new_id()}"
    tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "result": None
    }
    return {
        "a2a_version": "1.0",
        "message_id": new_id(),
        "session_id": msg.session_id,
        "sender": {"agent_id": "backend_agent"},
        "recipient": msg.sender.dict(),
        "type": "response",
        "reply_to": msg.message_id,
        "status": "accepted",
        "task_id": task_id,
        "payload": {"message": "文章生成中..."}
    }

# ------------------------------
# 2. SSE 流式接口（核心！）
# ------------------------------
def handle_chat_stream(msg: A2AMessage):
    prompt = msg.payload.get("prompt", "")
    if not prompt:
        return error_response(msg.message_id, "MISSING_PROMPT", "请输入问题")

    # 模拟 AI 流式输出文本
    async def event_generator():
        reply = f"你好！我是 A2A 智能体，我收到了你的问题：{prompt}。\n\n接下来我为你提供详细解答。\n\nAI 正在思考...\n\n流式输出就是这样逐字显示，和 ChatGPT 完全一样。"

        for char in reply:
            # 构造 A2A 标准流式消息
            chunk = {
                "a2a_version": "1.0",
                "message_id": new_id(),
                "session_id": msg.session_id,
                "type": "event",
                "event_type": "chunk",
                "task_id": new_id(),
                "payload": {"content": char}
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.03)  # 打字速度

        # 结束标记
        end = {"type": "event", "event_type": "done", "payload": {"status": "complete"}}
        yield f"data: {json.dumps(end)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ------------------------------
# 查询异步任务结果
# ------------------------------
@app.get("/a2a/v1/task/{task_id}")
async def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tasks[task_id]

# ------------------------------
# 工具函数
# ------------------------------
def new_id():
    return str(uuid.uuid4())[:8]

def error_response(reply_to: str, code: str, msg: str):
    return {
        "a2a_version": "1.0",
        "message_id": new_id(),
        "type": "error",
        "reply_to": reply_to,
        "error": {
            "code": code,
            "message": msg,
            "retryable": False
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
