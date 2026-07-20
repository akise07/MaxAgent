"""对话上下文管理器：将历史消息组装为 LangChain 消息列表。

职责：
- 从 SessionManager 读取历史消息
- 将历史消息（user/assistant role）转为 LangChain 的 HumanMessage / AIMessage
- 注入 SystemMessage（系统提示词）
- 支持截断策略（保留最近 N 轮对话，防止超长上下文）
- 提供 token 计数功能（使用 tiktoken 精确计算）
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import tiktoken
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config.prompts import get_system_prompt
from app.storage.session_store import SessionManager

# 保留的最大对话轮数（user + assistant 为一轮），超出则截断最早的历史
_MAX_TURNS = 50

# 默认编码（兼容大多数模型）
_DEFAULT_ENCODING = "cl100k_base"


def _get_encoding(model: str = "") -> str:
    """根据模型名返回 tiktoken 编码名称。"""
    try:
        enc = tiktoken.encoding_for_model(model or "gpt-4")
        return enc.name
    except Exception:
        return _DEFAULT_ENCODING


def count_context_tokens(
    conversation_id: str,
    session_manager: SessionManager,
    *,
    max_turns: int = _MAX_TURNS,
    model: str = "",
) -> int:
    """精确计算构建上下文后的总 token 数。

    参数：
        conversation_id: 会话 ID
        session_manager: 会话管理器实例
        max_turns: 保留的最大对话轮数
        model: 模型名（用于选择 tiktoken 编码，为空则用 cl100k_base）

    返回：
        总 token 数
    """
    enc_name = _get_encoding(model)
    try:
        enc = tiktoken.get_encoding(enc_name)
    except Exception:
        enc = tiktoken.get_encoding(_DEFAULT_ENCODING)

    total = 0

    # System prompt
    system_prompt = get_system_prompt()
    total += len(enc.encode(system_prompt))

    history = session_manager.get_messages(conversation_id)
    if not history:
        return total

    # 截断逻辑与 build_context 保持一致
    if max_turns > 0:
        max_messages = max_turns * 2
        if len(history) > max_messages:
            history = history[-max_messages:]

    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            total += len(enc.encode(content or ""))
            # assistant 的 thinking 内容也算
            if role == "assistant":
                thinking = msg.get("thinking", "")
                if thinking:
                    total += len(enc.encode(thinking))
            # 每条消息的开销（角色标记等）
            total += 4  # 每条消息约 4 token 的格式开销

    # 对话格式开销
    total += 3  # 对话首尾格式标记

    return total


def build_context(
    conversation_id: str,
    session_manager: SessionManager,
    *,
    max_turns: int = _MAX_TURNS,
    tools: list | None = None,
    include_skills: bool = False,
) -> list:
    """构建完整的对话上下文消息列表。

    返回 LangChain 消息列表，格式：
        [SystemMessage, HumanMessage, AIMessage, HumanMessage, ...]

    参数：
        conversation_id: 会话 ID
        session_manager: 会话管理器实例
        max_turns: 保留的最大对话轮数（超出则截断最早的历史）
        tools: 可用工具列表，非空时注入到 system prompt 末尾
        include_skills: 是否将 skills 描述注入到 system prompt 末尾
    """
    system_content = get_system_prompt()

    extra_parts = []

    if tools:
        from app.context.tool_loader import get_tool_descriptions
        tool_desc = get_tool_descriptions(tools)
        if tool_desc:
            extra_parts.append(tool_desc)

    if include_skills:
        from app.context.tool_loader import get_skill_descriptions
        skill_desc = get_skill_descriptions()
        if skill_desc:
            extra_parts.append(skill_desc)

    if extra_parts:
        system_content += "\n\n" + "\n\n".join(extra_parts)

    messages = [SystemMessage(content=system_content)]

    history = session_manager.get_messages(conversation_id)
    if not history:
        return messages

    # 截断：保留最近 max_turns 轮（每轮 = 1 条 user + 1 条 assistant）
    if max_turns > 0:
        max_messages = max_turns * 2
        if len(history) > max_messages:
            history = history[-max_messages:]

    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            thinking = msg.get("thinking")
            kwargs = {}
            if thinking:
                kwargs["additional_kwargs"] = {"reasoning_content": thinking}
            messages.append(AIMessage(content=content, **kwargs))
        # system role 忽略（已由 SystemMessage 注入）

    # 将上下文输出到 context.json（调试用）
    _dump_context(conversation_id, messages)

    return messages


def _dump_context(conversation_id: str, messages: list) -> None:
    """将上下文消息列表输出到 app/context/context.json。"""
    try:
        output = {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "role": type(m).__name__.replace("Message", "").lower() or "unknown",
                    "content": m.content,
                    "additional_kwargs": getattr(m, "additional_kwargs", None) or None,
                }
                for m in messages
            ],
        }
        path = Path(__file__).resolve().parent / "context.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 调试输出失败不影响主流程
