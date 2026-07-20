"""技能 API 路由：/api/skills*。"""
from __future__ import annotations

from fastapi import APIRouter

from app.context.skill_loader import list_skills

router = APIRouter()


@router.get("/api/skills")
async def api_list_skills():
    """获取所有可用技能列表。"""
    return {"skills": list_skills()}
