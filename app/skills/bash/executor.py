"""Bash 命令执行器。

在用户的 Windows 电脑上执行 PowerShell 命令并返回结果。
"""
from __future__ import annotations

import subprocess


def execute(command: str, timeout: int = 30) -> str:
    """执行 PowerShell 命令，返回格式化结果。"""
    if not command:
        return "请提供要执行的命令。"

    try:
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(f"**标准输出**：\n```\n{result.stdout.strip()}\n```")
        if result.stderr.strip():
            output_parts.append(f"**错误输出**：\n```\n{result.stderr.strip()}\n```")
        if result.returncode != 0:
            output_parts.append(f"**退出码**：{result.returncode}")
        if not output_parts:
            output_parts.append("命令执行成功（无输出）")
        return "\n\n".join(output_parts)
    except subprocess.TimeoutExpired:
        return f"命令执行超时（{timeout} 秒）"
    except Exception as e:
        return f"命令执行失败：{str(e)}"
