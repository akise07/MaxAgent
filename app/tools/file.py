"""文件操作工具：使用 langchain @tool 装饰器定义。"""
from __future__ import annotations

import os
import fnmatch
from pathlib import Path

from langchain_core.tools import tool


@tool
def find_files(
    pattern: str,
    root_dir: str = "",
    max_results: int = 50,
) -> str:
    """在指定目录下递归查找匹配的文件。

    当用户需要查找文件、搜索代码文件、定位资源时使用。
    支持通配符模式，如 *.py、*.txt、**/test* 等。

    参数：
        pattern: 文件通配符模式，如 *.py、data_*.csv、**/test*.py
        root_dir: 搜索根目录，为空则使用当前工作目录
        max_results: 最大返回结果数，默认 50
    """
    search_root = root_dir or os.getcwd()

    if not os.path.isdir(search_root):
        return f"错误：目录不存在 - {search_root}"

    results: list[str] = []

    try:
        for dirpath, dirnames, filenames in os.walk(search_root):
            # 跳过隐藏目录
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            # 跳过 node_modules、__pycache__、.git 等常见忽略目录
            dirnames[:] = [
                d
                for d in dirnames
                if d
                not in (
                    "node_modules",
                    "__pycache__",
                    ".git",
                    ".venv",
                    "venv",
                    ".idea",
                    ".vscode",
                )
            ]

            for filename in filenames:
                if fnmatch.fnmatch(filename, pattern):
                    full_path = os.path.join(dirpath, filename)
                    results.append(full_path)
                    if len(results) >= max_results:
                        break

            if len(results) >= max_results:
                break
    except PermissionError:
        pass  # 跳过无权限目录

    if not results:
        return f"在 {search_root} 下未找到匹配 {pattern} 的文件。"

    lines = [f"找到 {len(results)} 个匹配文件（{pattern}）：", ""]
    for r in results:
        try:
            rel = os.path.relpath(r, search_root)
            lines.append(f"  {rel}")
        except ValueError:
            lines.append(f"  {r}")

    if len(results) >= max_results:
        lines.append("")
        lines.append(f"（结果已截断，仅显示前 {max_results} 个）")

    return "\n".join(lines)


def get_tools() -> list:
    """tool_loader 统一接口：返回本模块定义的所有工具。"""
    return [find_files]
