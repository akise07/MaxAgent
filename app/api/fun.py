"""其他 API 接口封装：配置获取、聊天接口、打开目录等。"""
import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from config import Config
from main import build_agent
from app.api.sessions import SessionManager
from app.config.model import INTENSITY_TO_REASONING_EFFORT
from app.models_store import ModelConfigStore


# ===== 路由 =====
router = APIRouter()

# 全局对象（由 app.py 启动时注入）
_session_manager: SessionManager | None = None
_agent = None
_config: Config | None = None
_model_store: ModelConfigStore | None = None

# 项目根目录 / home 目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HOME_DIR = _PROJECT_ROOT / "home"


def _build_thinking_kwargs(advanced: dict | None) -> tuple[str | None, dict]:
    """根据模型的 advanced 配置，构造透传给 LLM 的参数。

    返回 (reasoning_effort, model_kwargs)：
    - reasoning_effort：OpenAI 顶层参数，值为 low/medium/high（None 表示不设置）
    - model_kwargs：传给底层的额外参数，例如 Qwen 风格的 chat_template_kwargs

    - thinking_mode 开启：把 default_thinking_intensity 映射为 reasoning_effort
      （低→low, 中→medium, 高/超高/极致→high）
    - thinking_only / allow_disable_thinking 开启：同时设置
      chat_template_kwargs.enable_thinking=True（Qwen 风格，常规 API 忽略）
    """
    if not advanced or not advanced.get("thinking_mode"):
        return None, {}
    intensity = advanced.get("default_thinking_intensity") or "高"
    effort = INTENSITY_TO_REASONING_EFFORT.get(intensity, "high")
    model_kwargs: dict = {}
    if advanced.get("thinking_only") or advanced.get("allow_disable_thinking"):
        model_kwargs["chat_template_kwargs"] = {"enable_thinking": True}
    return effort, model_kwargs


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


# ===== 数据模型 =====
class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model_id: str | None = None  # 可选：指定使用的已配置模型 uid
    # 可选：覆盖模型默认思考强度（必须仍在 supported_thinking_intensities 内）
    thinking_intensity: str | None = None
    # 可选：本次消息是否启用思考模式；None 表示遵循模型默认
    thinking_enabled: bool | None = None


def _resolve_llm_config(model_uid: str | None = None) -> dict:
    """从模型库或全局 Config 解析 LLM 参数。"""
    if _model_store is not None:
        model = None
        if model_uid:
            model = _model_store.get_model(model_uid, include_key=True)
        if model is None:
            model = _model_store.get_default(include_key=True)
        if model:
            return {
                "model": model.get("model_id") or model.get("name") or "hy3",
                "api_key": model.get("api_key") or "EMPTY",
                "base_url": model.get("api_endpoint") or "",
                "advanced": model.get("advanced") or {},
            }
    if _config is None:
        raise HTTPException(status_code=500, detail="配置未初始化")
    return {
        "model": _config.MODEL_NAME,
        "api_key": _config.API_KEY or "EMPTY",
        "base_url": _config.API_ENDPOINT,
        "advanced": {},
    }


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
        # 优先按请求指定模型 / 默认模型即时调用
        llm_cfg = _resolve_llm_config(req.model_id)
        # 合并：模型默认 + 本次请求的覆盖
        advanced_cfg = dict(llm_cfg.get("advanced") or {})
        if req.thinking_enabled is not None:
            advanced_cfg["thinking_mode"] = bool(req.thinking_enabled)
        if req.thinking_intensity:
            advanced_cfg["default_thinking_intensity"] = req.thinking_intensity
        reasoning_effort, model_kwargs = _build_thinking_kwargs(advanced_cfg)
        llm_kwargs: dict = {
            "model": llm_cfg["model"],
            "api_key": llm_cfg["api_key"],
            "base_url": llm_cfg["base_url"],
        }
        if reasoning_effort is not None:
            llm_kwargs["reasoning_effort"] = reasoning_effort
        if model_kwargs:
            llm_kwargs["model_kwargs"] = model_kwargs
        llm = ChatOpenAI(**llm_kwargs)
        response = llm.invoke(messages)
        reply = getattr(response, "content", None) or ""
        if not reply and _agent is not None:
            result = _agent.invoke({"messages": messages})
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
