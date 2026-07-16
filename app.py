import uvicorn
import webview
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import threading
import time
import os
import urllib.request

from main import build_agent
from config import Config

app = FastAPI(title="MaxAgent GUI")

# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 存储会话历史
conversations: dict[str, list[dict]] = {}
conversation_titles: dict[str, str] = {}
conversation_order: list[str] = []
agent = build_agent()
config = Config()


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


class NewConversationRequest(BaseModel):
    title: str = "新对话"


class RenameRequest(BaseModel):
    conversation_id: str
    title: str


@app.get("/")
async def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/config")
async def get_config():
    return {
        "api_endpoint": config.API_ENDPOINT,
        "model_name": config.MODEL_NAME,
    }


@app.post("/api/conversations/new")
async def new_conversation(req: NewConversationRequest):
    cid = str(int(time.time() * 1000))
    conversations[cid] = []
    conversation_titles[cid] = req.title
    conversation_order.insert(0, cid)
    return {"conversation_id": cid, "title": req.title}


@app.get("/api/conversations")
async def list_conversations():
    items = []
    for cid in conversation_order:
        msgs = conversations.get(cid, [])
        # 取第一条用户消息作为预览
        preview = ""
        for m in msgs:
            if m["role"] == "user":
                preview = m["content"][:50]
                break
        items.append({
            "id": cid,
            "title": conversation_titles.get(cid, "新对话"),
            "preview": preview,
            "message_count": len(msgs),
        })
    return {"conversations": items}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "conversation_id": conversation_id,
        "title": conversation_titles.get(conversation_id, "新对话"),
        "messages": conversations[conversation_id],
    }


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    del conversations[conversation_id]
    del conversation_titles[conversation_id]
    if conversation_id in conversation_order:
        conversation_order.remove(conversation_id)
    return {"ok": True}


@app.put("/api/conversations/rename")
async def rename_conversation(req: RenameRequest):
    if req.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    conversation_titles[req.conversation_id] = req.title
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 添加用户消息
    conversations[req.conversation_id].append({
        "role": "user",
        "content": req.message,
    })

    try:
        # 调用 agent
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content="你是一个有帮助的AI助手。请用中文回答。"),
            HumanMessage(content=req.message),
        ]
        result = agent.invoke({"messages": messages})
        reply = ""
        for msg in result["messages"]:
            if hasattr(msg, "content") and msg.content:
                reply = msg.content

        if not reply:
            reply = "抱歉，我没有生成有效的回复。"

        # 添加助手回复
        conversations[req.conversation_id].append({
            "role": "assistant",
            "content": reply,
        })

        return {"reply": reply}
    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        conversations[req.conversation_id].append({
            "role": "assistant",
            "content": error_msg,
        })
        return {"reply": error_msg}


def start_server():
    """在后台线程中启动 uvicorn 服务器"""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def wait_for_server(url="http://127.0.0.1:8000", timeout=10):
    """等待服务器就绪"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def create_window():
    """创建原生 Windows 窗口，内置浏览器加载页面"""
    window = webview.create_window(
        title="MaxAgent - AI 助手",
        url="http://127.0.0.1:8000",
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
    )
    return window


if __name__ == "__main__":
    # 在后台线程启动 FastAPI 服务器
    threading.Thread(target=start_server, daemon=True).start()
    # 等待服务器就绪
    if not wait_for_server():
        print("服务器启动超时")
    # 创建窗口并启动 GUI 事件循环
    create_window()
    webview.start()
