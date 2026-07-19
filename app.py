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
from starlette.requests import Request
from starlette.responses import Response

from app.api import chat as chat_api
from app.api import conversations
from app.api import models as models_api
from app.config.settings import Config
from app.api.debug import disable_hot_reload, enable_hot_reload
from app.services.agent import build_agent
from app.storage.models import ModelConfigStore
from app.storage.session_store import SessionManager


# ===== FastAPI 应用 =====
appFastAPI = FastAPI(title="MaxAgent GUI")

# 自定义访问日志，过滤热更新心跳
_SKIP_LOG_PATHS = {"/api/poll-reload", "/api/reload-frontend", "/favicon.ico"}


@appFastAPI.middleware("http")
async def _access_log(request: Request, call_next) -> Response:
    response = await call_next(request)
    if request.url.path not in _SKIP_LOG_PATHS:
        print(
            f"{request.client.host}:{request.client.port} - "
            f'"{request.method} {request.url.path} HTTP/{request.scope["http_version"]}" '
            f"{response.status_code}"
        )
    return response


# 静态资源目录
static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
appFastAPI.mount("/static", StaticFiles(directory=static_dir), name="static")

# 初始化依赖（会话管理 + Agent + 配置 + 模型列表）
session_manager = SessionManager()
agent = build_agent()
config = Config()
model_store = ModelConfigStore()
chat_api.init_dependencies(session_manager, agent, config, model_store)
conversations.init_dependencies(session_manager)
models_api.init_store(model_store)

# 注册路由
appFastAPI.include_router(chat_api.router)
appFastAPI.include_router(conversations.router)
appFastAPI.include_router(models_api.router)


@appFastAPI.get("/")
async def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


# ===== 服务器与窗口 =====
server: uvicorn.Server | None = None
debug_mode = False


def start_server():
    """在后台线程中启动 uvicorn 服务器。"""
    global server
    uv_config = uvicorn.Config(
        appFastAPI,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False,
        reload=debug_mode,
        reload_dirs=[os.path.dirname(__file__)] if debug_mode else None,
        reload_excludes=["app/static/**"] if debug_mode else None,
    )
    server = uvicorn.Server(uv_config)
    server.run()


def stop_server():
    """窗口关闭后停止 uvicorn，便于进程正常退出。"""
    if server is not None:
        server.should_exit = True


def wait_for_server(url="http://127.0.0.1:8000", timeout=15):
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


def main(debug: bool = False):
    """启动应用。

    Args:
        debug: 启用热更新（后端 reload + 前端文件监听自动刷新）。
    """
    global debug_mode
    debug_mode = debug

    if debug:
        enable_hot_reload(appFastAPI)

    # 后台启动 FastAPI 服务器
    threading.Thread(target=start_server, daemon=True).start()
    if not wait_for_server():
        print("服务器启动超时")
    # 创建窗口并启动 GUI 事件循环
    create_window()
    webview.start(debug=debug)
    # 兜底：事件循环结束后再确保服务器关闭
    if debug:
        disable_hot_reload()
    stop_server()


if __name__ == "__main__":
    main(debug=True)
