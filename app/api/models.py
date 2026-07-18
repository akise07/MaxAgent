"""模型配置 API：列表 / 增删改 / 设默认。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.requests import ModelCreateRequest, ModelUpdateRequest
from app.storage.models import ModelConfigStore

router = APIRouter()
_store: ModelConfigStore | None = None


def init_store(store: ModelConfigStore) -> None:
    global _store
    _store = store


def get_store() -> ModelConfigStore:
    if _store is None:
        raise HTTPException(status_code=500, detail="模型配置未初始化")
    return _store


@router.get("/api/models")
async def list_models():
    store = get_store()
    default = store.get_default(include_key=False)
    return {
        "models": store.list_models(mask_key=True),
        "default_model_id": default["id"] if default else None,
    }


@router.get("/api/models/{model_uid}")
async def get_model(model_uid: str):
    store = get_store()
    item = store.get_model(model_uid, include_key=False)
    if not item:
        raise HTTPException(status_code=404, detail="模型不存在")
    # 编辑页需要回填 endpoint 等，密钥仅返回是否存在
    full = store.get_model(model_uid, include_key=True) or {}
    item["api_key_placeholder"] = "••••••••" if full.get("api_key") else ""
    return item


@router.post("/api/models")
async def create_model(req: ModelCreateRequest):
    store = get_store()
    if not req.api_endpoint.strip() or not req.model_id.strip():
        raise HTTPException(status_code=400, detail="API 端点与模型 ID 不能为空")
    item = store.create_model(
        name=req.name or req.model_id,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        model_id=req.model_id,
        set_default=req.set_default,
        advanced=req.advanced.model_dump() if req.advanced else None,
    )
    return item


@router.put("/api/models/{model_uid}")
async def update_model(model_uid: str, req: ModelUpdateRequest):
    store = get_store()
    item = store.update_model(
        model_uid,
        name=req.name,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        model_id=req.model_id,
        set_default=req.set_default,
        advanced=req.advanced.model_dump() if req.advanced else None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="模型不存在")
    return item


@router.delete("/api/models/{model_uid}")
async def delete_model(model_uid: str):
    store = get_store()
    if not store.delete_model(model_uid):
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"ok": True}


@router.post("/api/models/{model_uid}/default")
async def set_default_model(model_uid: str):
    store = get_store()
    if not store.set_default(model_uid):
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"ok": True, "default_model_id": model_uid}
