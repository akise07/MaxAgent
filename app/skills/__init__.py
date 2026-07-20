"""技能数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillSpec:
    """技能元数据。"""
    name: str
    description: str
    icon: str = "🧩"
    category: str = "通用"
    when_to_use: str = ""
    parameters: dict = field(default_factory=dict)
    dir_path: str = ""  # 技能目录绝对路径，用于动态导入执行器
    body: str = ""  # skill.md 正文（去掉 YAML front matter）
