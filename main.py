"""MaxAgent CLI 入口：终端对话样例。

Agent 业务逻辑已抽至 app.services.agent，此处仅保留样例运行。
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.agent import build_agent


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
