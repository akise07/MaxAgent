"""工具加载器：自动扫描 app/tools/ 目录，加载所有工具模块。

约定：
- 每个 .py 文件（除 __init__.py、tool_loader.py）为一个工具模块
- 模块需导出 get_tools() -> list 函数，返回 langchain BaseTool 列表
- 加载器合并所有模块的工具，供 context 和 LLM 绑定使用
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from pathlib import Path

from app.context.skill_loader import get_skills


def load_all_tools() -> list:
    """扫描 app/tools/ 下所有模块，加载并返回所有工具。"""
    tools: list = []
    tools_dir = Path(__file__).resolve().parents[1] / "tools"

    for importer, modname, ispkg in pkgutil.iter_modules([str(tools_dir)]):
        if modname in ("tool_loader",):
            continue
        try:
            module = importlib.import_module(f"app.tools.{modname}")
            if hasattr(module, "get_tools"):
                module_tools = module.get_tools()
                if module_tools:
                    tools.extend(module_tools)
        except Exception as e:
            print(f"[tool_loader] 加载工具模块 {modname} 失败: {e}")

    return tools


def get_tool_descriptions(tools: list) -> str:
    """将工具列表格式化为 system prompt 可用的描述文本。"""
    if not tools:
        return ""

    lines = ["## 可用工具", ""]
    for t in tools:
        name = t.name
        desc = t.description.split(".")[0] if t.description else "暂无描述"
        args_desc = ""
        if hasattr(t, "args") and t.args:
            schema = t.args.schema() if hasattr(t.args, "schema") else {}
            props = schema.get("properties", {})
            if props:
                param_lines = []
                for pname, pinfo in props.items():
                    pdesc = pinfo.get("description", "")
                    required = "必填" if pname in (schema.get("required") or []) else "可选"
                    param_lines.append(f"  - {pname}（{required}）：{pdesc}")
                if param_lines:
                    args_desc = "\n参数：\n" + "\n".join(param_lines)

        lines.append(f"### {name}")
        lines.append(f"{desc}{args_desc}")
        lines.append("")

    return "\n".join(lines)


def get_skill_descriptions() -> str:
    """将 skills 目录下的技能完整 skill.md 注入到 system prompt。"""
    skills = get_skills()
    if not skills:
        return ""

    lines = ["## 可用技能", ""]
    for s in skills.values():
        if s.name == "bash":
            continue  # bash 已作为系统工具
        lines.append(f"### {s.icon} {s.name}（{s.category}）")
        lines.append("")
        if s.body:
            lines.append(s.body)
        else:
            lines.append(s.description or "暂无描述")
        lines.append("")

    return "\n".join(lines)
