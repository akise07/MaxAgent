"""聊天业务编排：LLM 参数解析、thinking 透传、调用流程。

从 app/api/fun.py 抽离的业务部分，改为显式参数（去模块全局变量），
便于测试与复用。HTTPException 留在路由层处理。
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config.model import THINKING_LEVELS
from app.config.prompts import get_system_prompt
from app.config.settings import Config
from app.storage.models import ModelConfigStore
from app.storage.session_store import SessionManager
from app.schemas.requests import ChatRequest


def build_thinking_kwargs(advanced: dict | None) -> tuple[str | None, dict]:
    """根据模型的 advanced 配置，构造透传给 LLM 的参数。

    返回 (reasoning_effort, model_kwargs)：
    - reasoning_effort：OpenAI 顶层参数，值为 high / None（None 表示不设置）
    - model_kwargs：传给底层的额外参数，例如 Qwen 风格的 chat_template_kwargs

    - thinking_mode 开启：把 default_thinking_intensity 直接作为 reasoning_effort
    - thinking_only / allow_disable_thinking 开启：同时设置
      chat_template_kwargs.enable_thinking=True（Qwen 风格，常规 API 忽略）
    """
    if not advanced or not advanced.get("thinking_mode"):
        return None, {}
    intensity = advanced.get("default_thinking_intensity") or "high"
    effort = intensity if intensity in THINKING_LEVELS else "high"
    model_kwargs: dict = {}
    if advanced.get("thinking_only") or advanced.get("allow_disable_thinking"):
        model_kwargs["chat_template_kwargs"] = {"enable_thinking": True}
    return effort, model_kwargs


def resolve_llm_config(
    model_store: ModelConfigStore | None,
    config: Config,
    model_uid: str | None = None,
) -> dict:
    """从模型库或全局 Config 解析 LLM 参数。"""
    if model_store is not None:
        model = None
        if model_uid:
            model = model_store.get_model(model_uid, include_key=True)
        if model is None:
            model = model_store.get_default(include_key=True)
        if model:
            return {
                "model": model.get("model_id") or model.get("name") or "hy3",
                "api_key": model.get("api_key") or "EMPTY",
                "base_url": model.get("api_endpoint") or "",
                "advanced": model.get("advanced") or {},
            }
    return {
        "model": config.MODEL_NAME,
        "api_key": config.API_KEY or "EMPTY",
        "base_url": config.API_ENDPOINT,
        "advanced": {},
    }


def run_chat(
    req: ChatRequest,
    session_manager: SessionManager,
    agent,
    model_store: ModelConfigStore | None,
    config: Config,
) -> dict:
    """聊天业务编排：标题生成、消息写入、LLM 调用、fallback、异常兜底。

    调用方需保证会话已存在（路由层校验）。返回 {"reply": ...}。
    """
    # 如果是首次用户消息，自动生成标题
    existing = session_manager.get_messages(req.conversation_id)
    if not existing:
        title = req.message.strip()[:20] or "新对话"
        session_manager.rename(req.conversation_id, title)

    # 写入用户消息
    session_manager.add_message(req.conversation_id, "user", req.message)

    try:
        messages = [
            SystemMessage(content=get_system_prompt()),
            HumanMessage(content=req.message),
        ]
        # 优先按请求指定模型 / 默认模型即时调用
        llm_cfg = resolve_llm_config(model_store, config, req.model_id)
        # 合并：模型默认 + 本次请求的覆盖
        advanced_cfg = dict(llm_cfg.get("advanced") or {})
        if req.thinking_enabled is not None:
            advanced_cfg["thinking_mode"] = bool(req.thinking_enabled)
        if req.thinking_intensity:
            advanced_cfg["default_thinking_intensity"] = req.thinking_intensity
        reasoning_effort, model_kwargs = build_thinking_kwargs(advanced_cfg)
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
        if not reply and agent is not None:
            result = agent.invoke({"messages": messages})
            for msg in result["messages"]:
                if hasattr(msg, "content") and msg.content:
                    reply = msg.content

        if not reply:
            reply = "抱歉，我没有生成有效的回复。"

        # 写入助手回复
        session_manager.add_message(req.conversation_id, "assistant", reply)
        return {"reply": reply}
    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        session_manager.add_message(req.conversation_id, "assistant", error_msg)
        return {"reply": error_msg}
