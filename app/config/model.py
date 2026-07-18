"""模型配置参数模板：数据类、常量与默认值工厂。

集中存放与模型参数结构相关的 Pydantic 数据类、枚举常量与工厂函数，
供 API / 存储层 / 运行时调用方共享引用。

约定
----
- `AdvancedConfig` 是 Pydantic 模型，用于 API 请求参数校验
- `default_advanced()` 返回 Python dict，用于存储层持久化
- 思考强度相关常量在此统一定义，避免散落各处
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ===== 思考强度档位（与 UI 强绑定，前端按此顺序渲染） =====
THINKING_LEVELS: list[str] = ["低", "中", "高", "超高", "极致"]


# ===== 思考强度中文 → OpenAI reasoning_effort 映射 =====
INTENSITY_TO_REASONING_EFFORT: dict[str, str] = {
    "低": "low",
    "中": "medium",
    "高": "high",
    "超高": "high",
    "极致": "high",
}


# ===== 高级配置 Pydantic 模型 =====
class AdvancedConfig(BaseModel):
    """模型高级配置参数模板。"""

    tool_calling: bool = False
    image_input: bool = False
    thinking_mode: bool = False
    thinking_only: bool = False
    allow_disable_thinking: bool = False
    default_thinking_intensity: str = "高"
    supported_thinking_intensities: list[str] = Field(default_factory=lambda: ["高"])
    context_input: int = 0
    context_output: int = 0


# ===== 默认值工厂 =====
def default_advanced() -> dict:
    """返回 advanced 字段的默认值 dict（供存储层持久化使用）。"""
    return {
        "tool_calling": False,
        "image_input": False,
        "thinking_mode": False,
        "thinking_only": False,
        "allow_disable_thinking": False,
        "default_thinking_intensity": "高",
        "supported_thinking_intensities": ["高"],
        "context_input": 0,
        "context_output": 0,
    }
