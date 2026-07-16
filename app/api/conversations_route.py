"""会话相关 API 路由封装。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.sessions import SessionManager


router = APIRouter()
_session_manager: SessionManager | None = None


def init_dependencies(session_manager: SessionManager) -> None:
    """由 app.py 在启动时调用，注入依赖。"""
    global _session_manager
    _session_manager = session_manager


# ===== 数据模型 =====
class NewConversationRequest(BaseModel):
    title: str = "新对话"


class RenameRequest(BaseModel):
    conversation_id: str
    title: str


# ===== 路由 =====
@router.get("/api/conversations")
async def list_conversations():
    if _session_manager is None:
        raise HTTPException(status_code=500, detail="会话管理器未初始化")
    return {"conversations": _session_manager.list_all()}


@router.post("/api/conversations/new")
async def new_conversation(req: NewConversationRequest):
    if _session_manager is None:
        raise HTTPException(status_code=500, detail="会话管理器未初始化")
    return _session_manager.create(req.title)


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    if _session_manager is None:
        raise HTTPException(status_code=500, detail="会话管理器未初始化")
    data = _session_manager.get(conversation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return data


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if _session_manager is None:
        raise HTTPException(status_code=500, detail="会话管理器未初始化")
    ok = _session_manager.delete(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.put("/api/conversations/rename")
async def rename_conversation(req: RenameRequest):
    if _session_manager is None:
        raise HTTPException(status_code=500, detail="会话管理器未初始化")
    ok = _session_manager.rename(req.conversation_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}
