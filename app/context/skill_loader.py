"""技能加载器：扫描 skills 目录下的子文件夹，从 skill.md 读取元数据。

设计原则：
- 技能是纯数据（skill.md），与 agent 程序逻辑完全隔离
- 参数结构完全由 skill.md 决定，加载器不做任何格式假设
- 执行器（executor.py）是可选的，存在时由 chat_service 动态调用
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from app.skills import SkillSpec

_skills: dict[str, SkillSpec] | None = None


def _parse_skill_md(filepath: str, dir_path: str = "") -> SkillSpec | None:
    """解析 skill.md 文件，返回 SkillSpec。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # 解析 YAML front matter
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return None

    front = match.group(1)
    body = match.group(2).strip()

    # 提取字段
    name = _extract_field(front, "name")
    if not name:
        # 用文件夹名称作为 skill 名称
        name = os.path.basename(dir_path) if dir_path else ""
    icon = _extract_field(front, "icon") or "🧩"
    category = _extract_field(front, "category") or "通用"

    if not name:
        return None

    # 提取第一段作为 description
    desc = ""
    for line in body.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("|"):
            desc = line
            break

    # 提取 #何时调用 部分
    when_to_use = ""
    when_match = re.search(r"#+\s*何时调用\s*\n(.*?)(?=\n#+\s|$)", body, re.DOTALL)
    if when_match:
        when_to_use = when_match.group(1).strip()

    # 参数结构完全由 skill.md 决定：
    # 1. 优先从 YAML front matter 读取 parameters（JSON Schema 格式）
    # 2. 回退从 Markdown 参数表解析
    parameters = _parse_parameters(front, body)

    return SkillSpec(
        name=name,
        description=desc or "暂无描述",
        icon=icon,
        category=category,
        when_to_use=when_to_use,
        parameters=parameters,
        dir_path=dir_path,
        body=body,
    )


def _parse_parameters(front: str, body: str) -> dict:
    """解析参数定义。

    优先级：
    1. YAML front matter 中的 parameters 字段（JSON Schema 格式）
    2. Markdown 参数表（| 参数 | 类型 | 必填 | 说明 |）
    """
    # 尝试从 YAML front matter 读取 parameters
    params_raw = _extract_multiline_field(front, "parameters")
    if params_raw:
        try:
            parsed = json.loads(params_raw)
            if isinstance(parsed, dict) and "properties" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # 回退：从 Markdown 参数表解析
    return _parse_parameters_table(body)


def _parse_parameters_table(body: str) -> dict:
    """从 Markdown 参数表解析为 OpenAI Tool JSON Schema 的 parameters。

    解析格式：
        | 参数 | 类型 | 必填 | 说明 |
        |------|------|------|------|
        | query | string | 是 | 搜索关键词 |
    """
    properties = {}
    required = []

    table_pattern = re.compile(r"^\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|", re.MULTILINE)
    rows = table_pattern.findall(body)

    # 跳过表头行（第一行是表头，第二行是分隔符）
    for row in rows[2:]:
        param_name = row[0].strip()
        param_type = row[1].strip().lower()
        is_required = "是" in row[2].strip() or "true" in row[2].strip().lower()
        param_desc = row[3].strip()

        if not param_name:
            continue

        # 类型映射
        type_map = {
            "string": "string",
            "number": "number",
            "integer": "integer",
            "boolean": "boolean",
            "array": "array",
            "object": "object",
        }
        json_type = type_map.get(param_type, "string")
        prop: dict[str, Any] = {"type": json_type, "description": param_desc}

        properties[param_name] = prop
        if is_required:
            required.append(param_name)

    if not properties:
        return {}

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


def _extract_field(front: str, key: str) -> str:
    """从 YAML front matter 中提取单行字段值。"""
    for line in front.split("\n"):
        line = line.strip()
        if line.startswith(f"{key}:"):
            val = line[len(key) + 1 :].strip().strip('"').strip("'")
            return val
    return ""


def _extract_multiline_field(front: str, key: str) -> str:
    """从 YAML front matter 中提取多行字段值（缩进块）。"""
    lines = front.split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}:"):
            # 收集后续缩进的行
            rest = []
            for subline in lines[i + 1 :]:
                if subline.startswith(" ") or subline.startswith("\t"):
                    rest.append(subline)
                else:
                    break
            if rest:
                return "\n".join(rest)
            # 单行 inline JSON
            val = line[len(key) + 1 :].strip()
            return val
    return ""


def _discover_skills() -> dict[str, SkillSpec]:
    """扫描 app/skills/ 下所有子文件夹，读取 skill.md。"""
    found: dict[str, SkillSpec] = {}
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")

    if not os.path.isdir(skills_dir):
        return found

    for entry in os.listdir(skills_dir):
        entry_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(entry_path) or entry.startswith("_"):
            continue
        md_path = os.path.join(entry_path, "skill.md")
        if not os.path.exists(md_path):
            continue
        spec = _parse_skill_md(md_path, dir_path=entry_path)
        if spec is not None:
            found[spec.name] = spec

    return found


def get_skills() -> dict[str, SkillSpec]:
    """获取所有已加载的技能（按名称索引）。"""
    global _skills
    if _skills is None:
        _skills = _discover_skills()
    return _skills


def get_skill(name: str) -> SkillSpec | None:
    """按名称获取技能元数据。"""
    return get_skills().get(name)


def list_skills() -> list[dict[str, Any]]:
    """返回技能列表（用于 API 输出）。"""
    return [
        {
            "name": s.name,
            "description": s.description,
            "icon": s.icon,
            "category": s.category,
        }
        for s in get_skills().values()
    ]


def build_openai_tools() -> list[dict]:
    """构建 OpenAI Tool Calling 格式的 tools 列表。

    参数结构完全由 skill.md 决定，加载器仅做透传。
    排除 bash 工具（由 app/tools/system.py 管理）。
    """
    tools = []
    for s in get_skills().values():
        if s.name == "bash":
            continue  # bash 由 system.py 的 @tool 装饰器管理
        tool = {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters or {"type": "object", "properties": {}},
            },
        }
        tools.append(tool)
    return tools
