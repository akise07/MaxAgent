"""对话上下文管理器：将历史消息组装为 LangChain 消息列表。

职责：
- 从 SessionManager 读取历史消息
- 将历史消息（user/assistant role）转为 LangChain 的 HumanMessage / AIMessage
- 注入 SystemMessage（系统提示词）
- 支持截断策略（保留最近 N 轮对话，防止超长上下文）
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config.prompts import get_system_prompt
from app.storage.session_store import SessionManager

# 保留的最大对话轮数（user + assistant 为一轮），超出则截断最早的历史
_MAX_TURNS = 50


def build_context(
    conversation_id: str,
    session_manager: SessionManager,
    *,
    max_turns: int = _MAX_TURNS,
) -> list:
    """构建完整的对话上下文消息列表。

    返回 LangChain 消息列表，格式：
        [SystemMessage, HumanMessage, AIMessage, HumanMessage, ...]

    参数：
        conversation_id: 会话 ID
        session_manager: 会话管理器实例
        max_turns: 保留的最大对话轮数（超出则截断最早的历史）
    """
    messages = [SystemMessage(content=get_system_prompt())]

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
            messages.append(AIMessage(content=content))
        # system role 忽略（已由 SystemMessage 注入）

    return messages
