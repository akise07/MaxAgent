"""聊天与杂项 API 路由：/api/chat、/api/config、/api/open-home。

业务编排已抽至 app.services.chat_service，此处仅负责路由分发、
依赖注入与 HTTP 异常包装。
"""
import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config.settings import Config
from app.context.context import count_context_tokens
from app.schemas.requests import ChatRequest
from app.services import chat_service
from app.storage.models import ModelConfigStore
from app.storage.session_store import SessionManager


# ===== 路由 =====
router = APIRouter()

# 全局对象（由 app.py 启动时注入）
_session_manager: SessionManager | None = None
"""会话管理器"""
_agent = None 
"""聊天代理"""
_config: Config | None = None
"""配置"""
_model_store: ModelConfigStore | None = None
"""模型配置存储"""

# 项目根目录 / home 目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HOME_DIR = _PROJECT_ROOT / "home"


def init_dependencies(
    session_manager: SessionManager,
    agent,
    config: Config,
    model_store: ModelConfigStore | None = None,
) -> None:
    """由 app.py 在启动时调用，注入依赖。"""
    global _session_manager, _agent, _config, _model_store
    _session_manager = session_manager
    _agent = agent
    _config = config
    _model_store = model_store


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
    default_model = None
    if _model_store is not None:
        default_model = _model_store.get_default(include_key=False)
    return {
        "api_endpoint": (
            default_model.get("api_endpoint")
            if default_model
            else _config.API_ENDPOINT
        ),
        "model_name": (
            default_model.get("model_id") or default_model.get("name")
            if default_model
            else _config.MODEL_NAME
        ),
        "default_model_id": default_model.get("id") if default_model else None,
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
    """处理用户消息：调用 LLM 生成回复。"""
    if _session_manager is None or _agent is None:
        raise HTTPException(status_code=500, detail="服务未初始化")
    if _config is None:
        raise HTTPException(status_code=500, detail="配置未初始化")

    if not _session_manager.exists(req.conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return chat_service.run_chat(
        req,
        session_manager=_session_manager,
        agent=_agent,
        model_store=_model_store,
        config=_config,
    )


@router.get("/api/chat/context-usage")
async def get_context_usage(conversation_id: str, model_id: str | None = None):
    """获取会话的上下文 token 使用量。

    查询参数：
        conversation_id: 会话 ID
        model_id: 模型 ID（用于选择 tiktoken 编码，可选）

    返回：
        {"used_tokens": int, "context_size": int}
    """
    if _session_manager is None:
        raise HTTPException(status_code=500, detail="服务未初始化")
    if not _session_manager.exists(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    # 获取模型 context_size
    context_size = 0
    if _model_store is not None and model_id:
        model = _model_store.get_model(model_id, include_key=False)
        if model:
            advanced = model.get("advanced") or {}
            context_size = int(advanced.get("context_size") or 0)

    # 获取模型名用于 tiktoken 编码选择
    model_name = ""
    if _model_store is not None and model_id:
        model = _model_store.get_model(model_id, include_key=False)
        if model:
            model_name = model.get("model_id") or model.get("name") or ""

    used_tokens = count_context_tokens(
        conversation_id,
        _session_manager,
        model=model_name,
    )

    return {
        "used_tokens": used_tokens,
        "context_size": context_size,
    }


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式聊天：以 SSE 格式逐块输出 token。"""
    if _session_manager is None or _agent is None:
        raise HTTPException(status_code=500, detail="服务未初始化")
    if _config is None:
        raise HTTPException(status_code=500, detail="配置未初始化")

    if not _session_manager.exists(req.conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return StreamingResponse(
        chat_service.run_chat_stream(
            req,
            session_manager=_session_manager,
            agent=_agent,
            model_store=_model_store,
            config=_config,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
