"""MaxAgent 桌面应用入口：整合 FastAPI 后端与 pywebview 窗口。"""
import os
import threading
import time
import urllib.request

import uvicorn
import webview
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat as chat_api
from app.api import conversations
from app.api import models as models_api
from app.config.settings import Config
from app.services.agent import build_agent
from app.storage.models import ModelConfigStore
from app.storage.session_store import SessionManager


# ===== FastAPI 应用 =====
app = FastAPI(title="MaxAgent GUI")

# 静态资源目录
static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 初始化依赖（会话管理 + Agent + 配置 + 模型列表）
session_manager = SessionManager()
agent = build_agent()
config = Config()
model_store = ModelConfigStore()
chat_api.init_dependencies(session_manager, agent, config, model_store)
conversations.init_dependencies(session_manager)
models_api.init_store(model_store)

# 注册路由
app.include_router(chat_api.router)
app.include_router(conversations.router)
app.include_router(models_api.router)


@app.get("/")
async def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


# ===== 服务器与窗口 =====
server: uvicorn.Server | None = None


def start_server():
    """在后台线程中启动 uvicorn 服务器。"""
    global server
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def stop_server():
    """窗口关闭后停止 uvicorn，便于进程正常退出。"""
    if server is not None:
        server.should_exit = True


def wait_for_server(url="http://127.0.0.1:8000", timeout=10):
    """等待服务器就绪。"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def create_window():
    """创建原生 Windows 窗口，内置浏览器加载页面。"""
    window = webview.create_window(
        title="MaxAgent - AI 助手",
        url="http://127.0.0.1:8000",
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
    )
    window.events.closed += stop_server
    return window


if __name__ == "__main__":
    # 后台启动 FastAPI 服务器
    threading.Thread(target=start_server, daemon=True).start()
    if not wait_for_server():
        print("服务器启动超时")
    # 创建窗口并启动 GUI 事件循环
    create_window()
    webview.start()
    # 兜底：事件循环结束后再确保服务器关闭
    stop_server()
