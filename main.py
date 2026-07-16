from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing import Annotated, TypedDict

from config import Config

config = Config()


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def create_llm() -> ChatOpenAI:
    """创建 LLM 实例"""
    return ChatOpenAI(
        model=config.MODEL_NAME,
        api_key=config.API_KEY,
        base_url=config.API_ENDPOINT,
    )


def call_model(state: AgentState) -> dict:
    """调用 LLM 生成回复"""
    llm = create_llm()
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """判断是否继续循环（简单实现：始终结束）"""
    return END


def build_agent() -> StateGraph:
    """构建 Agent 图"""
    graph = StateGraph(AgentState)

    graph.add_node("agent", call_model)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)

    return graph.compile()


def main():
    agent = build_agent()

    messages = [
        SystemMessage(content="你是一个有帮助的AI助手。"),
        HumanMessage(content="你好，请用一句话介绍你自己。"),
    ]

    result = agent.invoke({"messages": messages})
    for msg in result["messages"]:
        print(f"[{msg.type}]: {msg.content}")


if __name__ == "__main__":
    main()
