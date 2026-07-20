"""LangGraph Agent 构造：状态定义、LLM 工厂、节点函数与图装配。
"""
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.config.settings import Config

# 模块级配置实例：与原 main.py 行为一致，import 本模块即触发 load_dotenv
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
