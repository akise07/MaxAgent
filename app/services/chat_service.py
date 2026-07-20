"""聊天业务编排：LLM 参数解析、thinking 透传、LangGraph Agent Loop。

从 app/api/fun.py 抽离的业务部分，改为显式参数（去模块全局变量），
便于测试与复用。HTTPException 留在路由层处理。

Agent Loop 流程（由 LangGraph 驱动）：
1. 构建上下文消息（含 SystemMessage + 历史）
2. 用 bind_tools 将技能注册为 OpenAI tools
3. 构建 LangGraph agent（agent 节点 + tools 节点 + 条件边循环）
4. agent.invoke() / agent.astream() 自动处理多轮 tool calling
5. 将最终回复返回给用户

流式输出（run_chat_stream）：
- 通过 agent.astream_events() 获取每个节点的流式事件
- 逐块 yield token/thinking/tool_call/tool_result/done/error
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

# ---- Monkey-patch: 让 langchain_openai 保留 reasoning_content ----
# 必须在 ChatOpenAI 导入之前 patch，确保 _convert_delta_to_message_chunk 已被替换
import langchain_openai.chat_models.base as _lc_base
_orig_convert = _lc_base._convert_delta_to_message_chunk

def _patched_convert_delta_to_message_chunk(_dict, default_class):
    chunk = _orig_convert(_dict, default_class)
    reasoning = _dict.get("reasoning_content")
    if reasoning and isinstance(chunk, AIMessageChunk):
        extra = dict(chunk.additional_kwargs)
        extra["reasoning_content"] = reasoning
        chunk.additional_kwargs = extra
    return chunk

_lc_base._convert_delta_to_message_chunk = _patched_convert_delta_to_message_chunk
# ---- End monkey-patch ----

from langchain_openai import ChatOpenAI

from app.config.model import THINKING_LEVELS
from app.config.settings import Config
from app.context.context import build_context
from app.context.skill_loader import build_openai_tools, get_skill
from app.context.tool_loader import load_all_tools
from app.services.agent import build_agent
from app.storage.models import ModelConfigStore
from app.storage.session_store import SessionManager
from app.schemas.requests import ChatRequest


def build_thinking_kwargs(advanced: dict | None) -> tuple[str | None, dict, dict | None]:
    """根据模型的 advanced 配置，构造透传给 LLM 的参数。

    返回 (reasoning_effort, model_kwargs, extra_body)：
    - reasoning_effort：OpenAI 顶层参数，值为 high / None（None 表示不设置）
    - model_kwargs：传给底层的额外参数，例如 Qwen 风格的 chat_template_kwargs
    - extra_body：传给底层的额外请求体参数，例如 thinking 启用

    - thinking_mode 开启：把 default_thinking_intensity 直接作为 reasoning_effort
    - thinking_only / allow_disable_thinking 开启：同时设置
      chat_template_kwargs.enable_thinking=True（Qwen 风格，常规 API 忽略）
    """
    if not advanced or not advanced.get("thinking_mode"):
        return None, {}, None
    intensity = advanced.get("default_thinking_intensity") or "high"
    effort = intensity if intensity in THINKING_LEVELS else "high"
    model_kwargs: dict = {}
    extra_body: dict | None = {"thinking": {"type": "enabled"}}
    if advanced.get("thinking_only") or advanced.get("allow_disable_thinking"):
        model_kwargs["chat_template_kwargs"] = {"enable_thinking": True}
    return effort, model_kwargs, extra_body


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


def _read_skill_md(skill_name: str) -> str:
    """读取 skill.md 正文（去掉 YAML front matter）。"""
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
    md_path = os.path.join(skills_dir, skill_name, "skill.md")
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    return re.sub(r"^---.*?---\s*", "", content, count=1, flags=re.DOTALL).strip()


def _build_llm(
    req,
    model_store: ModelConfigStore | None,
    config: Config,
) -> tuple[ChatOpenAI, list]:
    """根据请求和配置构建 LLM 实例（含工具绑定）。

    返回 (llm, system_tools)。
    """
    llm_cfg = resolve_llm_config(model_store, config, req.model_id)
    advanced_cfg = dict(llm_cfg.get("advanced") or {})
    if req.thinking_enabled is not None:
        advanced_cfg["thinking_mode"] = bool(req.thinking_enabled)
    if req.thinking_intensity:
        advanced_cfg["default_thinking_intensity"] = req.thinking_intensity
    reasoning_effort, model_kwargs, extra_body = build_thinking_kwargs(advanced_cfg)

    llm_kwargs: dict = {
        "model": llm_cfg["model"],
        "api_key": llm_cfg["api_key"],
        "base_url": llm_cfg["base_url"],
    }
    if reasoning_effort is not None:
        llm_kwargs["reasoning_effort"] = reasoning_effort
    if extra_body:
        if model_kwargs:
            model_kwargs["extra_body"] = extra_body
        else:
            model_kwargs = {"extra_body": extra_body}
    if model_kwargs:
        llm_kwargs["model_kwargs"] = model_kwargs

    tools = build_openai_tools()
    system_tools = load_all_tools()
    llm = ChatOpenAI(**llm_kwargs)
    if tools:
        llm = llm.bind_tools(tools)
    if system_tools:
        llm = llm.bind_tools(system_tools)
    return llm, system_tools


def _ensure_title(req, session_manager: SessionManager) -> None:
    """首次消息自动生成标题。"""
    existing = session_manager.get_messages(req.conversation_id)
    if not existing:
        title = req.message.strip()[:20] or "新对话"
        session_manager.rename(req.conversation_id, title)


def _execute_tool(tool_name: str, arguments: dict) -> str:
    """执行工具调用，返回结果文本。

    优先级：
    1. 系统内置工具（app/tools/ 下的 @tool 装饰器工具）
    2. 技能目录下的 executor.py 动态导入
    3. 回退到读取 skill.md 返回文档内容
    """
    # 1. 尝试系统内置工具
    for t in load_all_tools():
        if t.name == tool_name:
            return t.invoke(arguments)

    skill = get_skill(tool_name)
    if skill is None:
        return f"未知工具：{tool_name}"

    # 2. 通过技能目录绝对路径动态导入 executor.py
    executor_path = os.path.join(skill.dir_path, "executor.py")
    if os.path.isfile(executor_path):
        try:
            spec = importlib.util.spec_from_file_location(
                f"{tool_name}.executor", executor_path
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "execute"):
                    return mod.execute(**arguments)
        except Exception as e:
            return f"工具 {tool_name} 执行失败：{str(e)}"

    # 回退：读取 skill.md 内容返回
    try:
        body = _read_skill_md(tool_name)
        args_desc = ""
        if arguments:
            args_desc = "\n\n**调用参数**：\n" + "\n".join(
                f"- {k}: {v}" for k, v in arguments.items()
            )
        return f"**{skill.icon} {skill.name}**\n\n{body}{args_desc}"
    except Exception as e:
        return f"工具 {tool_name} 执行失败：{str(e)}"


def run_chat(
    req,
    session_manager: SessionManager,
    model_store: ModelConfigStore | None,
    config: Config,
) -> dict:
    """聊天业务编排：标题生成、消息写入、LangGraph Agent Loop 调用。

    调用方需保证会话已存在（路由层校验）。返回 {"reply": ...}。
    """
    _ensure_title(req, session_manager)
    session_manager.add_message(req.conversation_id, "user", req.message)

    try:
        llm, system_tools = _build_llm(req, model_store, config)
        messages = build_context(req.conversation_id, session_manager, tools=system_tools, include_skills=True)

        # 构建 LangGraph agent loop
        agent_graph = build_agent(llm, _execute_tool)
        result = agent_graph.invoke({"messages": messages, "iteration_count": 0})

        # 提取最终回复（最后一条 AIMessage 的 content）
        reply = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                reply = msg.content
                break

        session_manager.add_message(req.conversation_id, "assistant", reply or "抱歉，我没有生成有效的回复。")
        return {"reply": reply}
    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        session_manager.add_message(req.conversation_id, "assistant", error_msg)
        return {"reply": error_msg}


async def run_chat_stream(
    req,
    session_manager: SessionManager,
    model_store: ModelConfigStore | None,
    config: Config,
) -> AsyncGenerator[str, None]:
    """流式聊天：以 SSE 格式逐块输出 token。

    通过 LangGraph agent.astream_events() 获取每个节点的流式事件。

    事件类型：
    - data: {"type": "token", "content": "..."}  — 普通 token
    - data: {"type": "thinking", "content": "..."}  — 思维链
    - data: {"type": "tool_call", "name": "...", "args": {...}, "id": "..."}  — 工具调用
    - data: {"type": "tool_result", "name": "...", "content": "...", "id": "..."}  — 工具执行结果
    - data: {"type": "done", "content": "..."}  — 完整回复
    - data: {"type": "error", "content": "..."}  — 错误信息
    """
    _ensure_title(req, session_manager)
    session_manager.add_message(req.conversation_id, "user", req.message)

    try:
        llm, system_tools = _build_llm(req, model_store, config)
        messages = build_context(req.conversation_id, session_manager, tools=system_tools, include_skills=True)

        # 构建 LangGraph agent loop
        agent_graph = build_agent(llm, _execute_tool)

        collected_content = ""
        collected_thinking = ""
        current_thinking = ""  # 当前轮次的 thinking

        async for event in agent_graph.astream_events(
            {"messages": messages, "iteration_count": 0},
            version="v2",
        ):
            kind = event.get("event", "")

            # ---- LLM 流式输出 ----
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if not isinstance(chunk, AIMessageChunk):
                    continue

                # 提取 reasoning_content（思维链）
                reasoning = chunk.additional_kwargs.get("reasoning_content", "") if chunk.additional_kwargs else ""
                if reasoning:
                    current_thinking += reasoning
                    collected_thinking += reasoning
                    yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"

                if chunk.content:
                    collected_content += chunk.content
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

            # ---- 工具调用开始 ----
            elif kind == "on_tool_start":
                # 将第一轮的 thinking 存储为 assistant 消息
                if collected_thinking or collected_content:
                    session_manager.add_message(
                        req.conversation_id, "assistant", collected_content or "",
                        thinking=collected_thinking or None,
                    )
                    # 重置累积变量，准备第二轮
                    collected_thinking = ""
                    collected_content = ""
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input", {})
                tool_id = event.get("run_id", "")
                # 存储 tool_call 信息到会话（用于刷新后渲染 tool 行）
                session_manager.add_message(
                    req.conversation_id, "assistant", "",
                    tool_calls=[{"name": tool_name, "args": tool_input, "id": tool_id}],
                )
                yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'args': tool_input, 'id': tool_id})}\n\n"

            # ---- 工具调用结束 ----
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                tool_output = event.get("data", {}).get("output", "")
                tool_id = event.get("run_id", "")
                # tool_output 是 ToolMessage，提取 content
                if hasattr(tool_output, "content"):
                    tool_output = tool_output.content
                # 存储 tool 消息到会话
                session_manager.add_message(
                    req.conversation_id, "tool", str(tool_output),
                    tool_call_id=tool_id,
                )
                yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'content': str(tool_output), 'id': tool_id})}\n\n"

        # 最终回复
        reply = collected_content
        session_manager.add_message(
            req.conversation_id, "assistant", reply or "抱歉，我没有生成有效的回复。",
            thinking=collected_thinking or None,
        )
        yield f"data: {json.dumps({'type': 'done', 'content': reply})}\n\n"

    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        session_manager.add_message(req.conversation_id, "assistant", error_msg)
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
