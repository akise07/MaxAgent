"""API 请求体 DTO：集中定义各路由的 Pydantic 请求模型。

从各路由文件抽离，便于路由层保持精简、DTO 统一管理。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.config.model import AdvancedConfig


# ===== /api/chat =====
class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model_id: str | None = None  # 可选：指定使用的已配置模型 uid
    # 可选：覆盖模型默认思考强度（必须仍在 supported_thinking_intensities 内）
    thinking_intensity: str | None = None
    # 可选：本次消息是否启用思考模式；None 表示遵循模型默认
    thinking_enabled: bool | None = None


# ===== /api/conversations* =====
class NewConversationRequest(BaseModel):
    title: str = "新对话"


class RenameRequest(BaseModel):
    conversation_id: str
    title: str


# ===== /api/models* =====
class ModelCreateRequest(BaseModel):
    name: str = ""
    api_endpoint: str
    api_key: str = ""
    model_id: str
    set_default: bool = False
    advanced: AdvancedConfig | None = None


class ModelUpdateRequest(BaseModel):
    name: str | None = None
    api_endpoint: str | None = None
    api_key: str | None = Field(
        default=None, description="留空或不传表示不修改密钥"
    )
    model_id: str | None = None
    set_default: bool | None = None
    advanced: AdvancedConfig | None = None
