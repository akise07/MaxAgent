"""系统内置工具：使用 langchain @tool 装饰器定义。

这些工具与 skills 目录下的技能不同：
- skills 是用户可配置的，通过 skill.md 定义，executor.py 动态加载
- system 工具是内置的，直接使用 @tool 装饰器注册，始终可用
"""
from __future__ import annotations

import subprocess

from langchain_core.tools import tool


@tool
def bash(command: str) -> str:
    """在用户的 Windows 电脑上执行 CMD 命令并返回结果。

    当用户要求执行系统命令、运行脚本、操作文件、安装软件、
    查看系统信息、管理进程等需要执行终端命令的操作时使用。
    必须确保传入的命令参数是CMD命令
    如果传入的命令带python代码，优先尝试直接运行该代码，执行python -c \"python代码\"，如果你没法通过修改这串指令来保证成功运行python代码，就尝试写一个临时python脚本来运行

    参数：
        command: 要执行的 CMD 命令
    """
    if not command:
        return "请提供要执行的命令。"

    try:
        result = subprocess.run(
            ["cmd", "/c", command],
            capture_output=True,
            timeout=30,
        )
        # CMD 默认使用 GBK 编码输出，手动解码
        def _decode(data: bytes) -> str:
            if not data:
                return ""
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

        output_parts = []
        stdout = _decode(result.stdout)
        stderr = _decode(result.stderr)
        if stdout.strip():
            output_parts.append(f"**标准输出**：\n```\n{stdout.strip()}\n```")
        if stderr.strip():
            output_parts.append(f"**错误输出**：\n```\n{stderr.strip()}\n```")
        if result.returncode != 0:
            output_parts.append(f"**退出码**：{result.returncode}")
        if not output_parts:
            output_parts.append("命令执行成功（无输出）")
        return "\n\n".join(output_parts)
    except subprocess.TimeoutExpired:
        return "命令执行超时（30 秒）"
    except Exception as e:
        return f"命令执行失败：{str(e)}"


def get_system_tools() -> list:
    """返回所有系统内置工具的列表。"""
    return [bash]


def get_tools() -> list:
    """tool_loader 统一接口：返回本模块定义的所有工具。"""
    return get_system_tools()
