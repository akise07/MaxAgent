"""其他 API 接口封装：配置获取、聊天接口、打开目录等。"""
import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from config import Config
from main import build_agent
from app.api.sessions import SessionManager


# ===== 路由 =====
router = APIRouter()

# 全局对象（由 app.py 启动时注入）
_session_manager: SessionManager | None = None
_agent = None
_config: Config | None = None

# 项目根目录 / home 目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HOME_DIR = _PROJECT_ROOT / "home"


def init_dependencies(session_manager: SessionManager, agent, config: Config) -> None:
    """由 app.py 在启动时调用，注入依赖。"""
    global _session_manager, _agent, _config
    _session_manager = session_manager
    _agent = agent
    _config = config


# ===== 数据模型 =====
class ChatRequest(BaseModel):
    conversation_id: str
    message: str


def _open_in_file_manager(path: Path) -> None:
    """用系统文件管理器打开目录。"""
    target = str(path.resolve())
    system = platform.system()
    if system == "Windows":
        os.startfile(target)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


# ===== 接口 =====
@router.get("/api/config")
async def get_config():
    """返回前端展示用的配置信息。"""
    if _config is None:
        raise HTTPException(status_code=500, detail="配置未初始化")
    return {
        "api_endpoint": _config.API_ENDPOINT,
        "model_name": _config.MODEL_NAME,
        "home_dir": str(_HOME_DIR.resolve()),
    }


@router.post("/api/open-home")
async def open_home():
    """在系统文件管理器中打开项目 home 目录。"""
    try:
        _HOME_DIR.mkdir(parents=True, exist_ok=True)
        _open_in_file_manager(_HOME_DIR)
        return {"ok": True, "path": str(_HOME_DIR.resolve())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开 Home 目录失败: {e}") from e


@router.post("/api/chat")
async def chat(req: ChatRequest):
    """处理用户消息：调用 Agent 生成回复。"""
    if _session_manager is None or _agent is None:
        raise HTTPException(status_code=500, detail="服务未初始化")

    if not _session_manager.exists(req.conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    # 如果是首次用户消息，自动生成标题
    existing = _session_manager.get_messages(req.conversation_id)
    if not existing:
        title = req.message.strip()[:20] or "新对话"
        _session_manager.rename(req.conversation_id, title)

    # 写入用户消息
    _session_manager.add_message(req.conversation_id, "user", req.message)

    try:
        messages = [
            SystemMessage(content="你是一个有帮助的AI助手。请用中文回答。"),
            HumanMessage(content=req.message),
        ]
        result = _agent.invoke({"messages": messages})
        reply = ""
        for msg in result["messages"]:
            if hasattr(msg, "content") and msg.content:
                reply = msg.content

        if not reply:
            reply = "抱歉，我没有生成有效的回复。"

        # 写入助手回复
        _session_manager.add_message(req.conversation_id, "assistant", reply)
        return {"reply": reply}
    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        _session_manager.add_message(req.conversation_id, "assistant", error_msg)
        return {"reply": error_msg}
