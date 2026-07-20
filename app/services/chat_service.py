"""聊天业务编排：LLM 参数解析、thinking 透传、Tool Calling 调用流程。

从 app/api/fun.py 抽离的业务部分，改为显式参数（去模块全局变量），
便于测试与复用。HTTPException 留在路由层处理。

Tool Calling 流程：
1. 构建上下文消息（含 SystemMessage + 历史）
2. 用 bind_tools 将技能注册为 OpenAI tools
3. LLM 返回 response.tool_calls → 执行对应技能 → 结果追加到消息列表
4. 将最终回复返回给用户

流式输出（run_chat_stream）：
- 第一轮流式输出：逐块 yield token，遇到 tool_calls 时 yield 特殊事件
- 执行工具后，第二轮流式输出最终回复
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
) -> ChatOpenAI:
    """根据请求和配置构建 LLM 实例（含工具绑定）。"""
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
    agent,
    model_store: ModelConfigStore | None,
    config: Config,
) -> dict:
    """聊天业务编排：标题生成、消息写入、LLM 调用、Tool Calling、fallback。

    调用方需保证会话已存在（路由层校验）。返回 {"reply": ...}。
    """
    _ensure_title(req, session_manager)
    session_manager.add_message(req.conversation_id, "user", req.message)

    try:
        llm, system_tools = _build_llm(req, model_store, config)
        messages = build_context(req.conversation_id, session_manager, tools=system_tools, include_skills=True)

        # 第一轮调用：LLM 可能返回 tool_calls
        response = llm.invoke(messages)

        # 处理 tool_calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            messages.append(response)
            for tc in response.tool_calls:
                result = _execute_tool(tc.get("name", ""), tc.get("args", {}))
                messages.append(
                    ToolMessage(content=result, tool_call_id=tc.get("id", ""))
                )
            # 第二轮调用
            response = llm.invoke(messages)

        reply = getattr(response, "content", None) or ""
        if not reply and agent is not None:
            result = agent.invoke({"messages": messages})
            for msg in result["messages"]:
                if hasattr(msg, "content") and msg.content:
                    reply = msg.content

        session_manager.add_message(req.conversation_id, "assistant", reply or "抱歉，我没有生成有效的回复。")
        return {"reply": reply}
    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        session_manager.add_message(req.conversation_id, "assistant", error_msg)
        return {"reply": error_msg}


async def run_chat_stream(
    req,
    session_manager: SessionManager,
    agent,
    model_store: ModelConfigStore | None,
    config: Config,
) -> AsyncGenerator[str, None]:
    """流式聊天：以 SSE 格式逐块输出 token。

    事件类型：
    - data: {"type": "token", "content": "..."}  — 普通 token
    - data: {"type": "tool_call", "name": "...", "args": {...}}  — 工具调用
    - data: {"type": "tool_result", "name": "...", "content": "..."}  — 工具执行结果
    - data: {"type": "done", "content": "..."}  — 完整回复
    - data: {"type": "error", "content": "..."}  — 错误信息
    """
    _ensure_title(req, session_manager)
    session_manager.add_message(req.conversation_id, "user", req.message)

    try:
        llm, system_tools = _build_llm(req, model_store, config)
        messages = build_context(req.conversation_id, session_manager, tools=system_tools, include_skills=True)

        # ---- 第一轮流式调用 ----
        collected_content = ""
        collected_thinking = ""
        collected_tool_calls: list[dict] = []

        async for chunk in llm.astream(messages):
            if not isinstance(chunk, AIMessageChunk):
                continue

            # 提取 reasoning_content（思维链）
            reasoning = chunk.additional_kwargs.get("reasoning_content", "") if chunk.additional_kwargs else ""

            if reasoning:
                collected_thinking += reasoning
                yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"

            if chunk.content:
                collected_content += chunk.content
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

            if chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    if isinstance(tc_chunk, dict):
                        idx = tc_chunk.get('index', 0)
                        name_val = tc_chunk.get('name', '') or ''
                        args_val = tc_chunk.get('args', '') or ''
                        id_val = tc_chunk.get('id', '') or ''
                    else:
                        idx = tc_chunk.index if tc_chunk.index is not None else 0
                        name_val = tc_chunk.name or ''
                        args_val = tc_chunk.args or ''
                        id_val = tc_chunk.id or ''
                    while len(collected_tool_calls) <= idx:
                        collected_tool_calls.append({"name": "", "args": "", "id": ""})
                    if name_val:
                        collected_tool_calls[idx]["name"] = name_val
                    if args_val:
                        collected_tool_calls[idx]["args"] += args_val
                    if id_val:
                        collected_tool_calls[idx]["id"] = id_val

        has_tool_calls = any(
            tc.get("name") and tc.get("args") for tc in collected_tool_calls
        )

        if has_tool_calls:
            # 解析完整的 tool_calls
            parsed_tool_calls = []
            for tc in collected_tool_calls:
                try:
                    args = json.loads(tc["args"]) if tc["args"] else {}
                except json.JSONDecodeError:
                    args = {}
                parsed_tool_calls.append({
                    "name": tc["name"],
                    "args": args,
                    "id": tc["id"] or f"call_{tc['name']}",
                })

            # 发送 tool_call 事件 + 写入会话存储
            for tc in parsed_tool_calls:
                yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'args': tc['args'], 'id': tc['id']})}\n\n"
            session_manager.add_message(
                req.conversation_id, "assistant", collected_content or "",
                tool_calls=[{"name": tc["name"], "args": tc["args"], "id": tc["id"]} for tc in parsed_tool_calls],
                thinking=collected_thinking or None,
            )

            # 加入内存消息列表（用于第二轮调用）
            assistant_msg = AIMessage(
                content=collected_content or "",
                tool_calls=[{"name": tc["name"], "args": tc["args"], "id": tc["id"]} for tc in parsed_tool_calls],
            )
            messages.append(assistant_msg)

            # 逐个执行工具
            for tc in parsed_tool_calls:
                result = _execute_tool(tc["name"], tc["args"])
                yield f"data: {json.dumps({'type': 'tool_result', 'name': tc['name'], 'content': result, 'id': tc['id']})}\n\n"
                session_manager.add_message(req.conversation_id, "tool", result, tool_call_id=tc["id"])
                messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

            # ---- 第二轮流式调用 ----
            collected_content = ""
            collected_thinking = ""
            async for chunk in llm.astream(messages):
                # 提取 reasoning_content（思维链）
                reasoning = chunk.additional_kwargs.get("reasoning_content", "") if isinstance(chunk, AIMessageChunk) and chunk.additional_kwargs else ""
                if reasoning:
                    collected_thinking += reasoning
                    yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    collected_content += chunk.content
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"

        # 最终回复
        reply = collected_content
        if not reply and agent is not None:
            result = agent.invoke({"messages": messages})
            for msg in result["messages"]:
                if hasattr(msg, "content") and msg.content:
                    reply = msg.content

        session_manager.add_message(
            req.conversation_id, "assistant", reply or "抱歉，我没有生成有效的回复。",
            thinking=collected_thinking or None,
        )
        yield f"data: {json.dumps({'type': 'done', 'content': reply})}\n\n"

    except Exception as e:
        error_msg = f"调用 Agent 时出错: {str(e)}"
        session_manager.add_message(req.conversation_id, "assistant", error_msg)
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
