"""LangGraph Agent 构造：状态定义、LLM 工厂、节点函数与图装配。

Agent Loop 流程：
    START → agent（LLM 调用）
              │
              ├─ 无 tool_calls → END（返回最终回复）
              └─ 有 tool_calls → tools（执行工具）→ agent（继续思考）
                                      ↑________________________|

支持多轮工具调用循环，直到 LLM 不再请求工具或达到最大迭代次数。
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# 最大工具调用循环次数（防止无限循环）
_MAX_ITERATIONS = 10


class AgentState(TypedDict):
    """Agent 状态：仅包含消息列表（LangGraph 自动合并）。"""
    messages: Annotated[list, add_messages]
    iteration_count: int


def _call_model(state: AgentState, llm) -> dict:
    """Agent 节点：调用 LLM 生成回复或工具调用请求。"""
    response = llm.invoke(state["messages"])
    return {
        "messages": [response],
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


def _execute_tools(state: AgentState, tool_executor) -> dict:
    """Tools 节点：执行 LLM 请求的工具调用，返回 ToolMessage 列表。"""
    last_message = state["messages"][-1]
    tool_messages = []
    for tc in last_message.tool_calls:
        result = tool_executor(tc["name"], tc.get("args", {}))
        tool_messages.append(
            ToolMessage(content=result, tool_call_id=tc["id"])
        )
    return {"messages": tool_messages}


def _should_continue(state: AgentState) -> str:
    """条件边：判断是否继续循环。

    返回 "tools" 继续执行工具，"__end__" 结束。
    """
    messages = state["messages"]
    if not messages:
        return END

    last_message = messages[-1]

    # 有 tool_calls → 继续执行工具
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # 检查是否超过最大迭代次数
        if state.get("iteration_count", 0) >= _MAX_ITERATIONS:
            return END
        return "tools"

    # 无 tool_calls → 结束
    return END


def build_agent(llm, tool_executor) -> StateGraph:
    """构建 LangGraph Agent 图。

    参数：
        llm: 已绑定工具的 ChatOpenAI 实例
        tool_executor: 工具执行函数，签名为 (tool_name: str, arguments: dict) -> str

    返回：
        编译后的 StateGraph（可调用 .invoke() / .astream()）
    """
    graph = StateGraph(AgentState)

    # 使用闭包捕获 llm 和 tool_executor
    def agent_node(state: AgentState) -> dict:
        return _call_model(state, llm)

    def tools_node(state: AgentState) -> dict:
        return _execute_tools(state, tool_executor)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)

    graph.set_entry_point("agent")

    # agent → 条件边：有 tool_calls 去 tools，否则 END
    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", END: END},
    )

    # tools → agent（执行完工具后继续思考）
    graph.add_edge("tools", "agent")

    return graph.compile()
