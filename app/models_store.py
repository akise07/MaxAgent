"""模型配置管理：持久化多模型列表，支持增删改查与默认模型。"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from app.config.model import THINKING_LEVELS, default_advanced


def _default_advanced() -> dict[str, Any]:
    """模型高级配置的默认结构（与 UI 字段一一对应）。"""
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


class ModelConfigStore:
    """管理已配置模型列表，存储于 home/config/models.json。"""

    def _normalize_advanced(self, raw: Any) -> dict[str, Any]:
        """兜底：把外部传入的 advanced 规整为标准结构，缺字段自动补默认。"""
        base = default_advanced()
        if not isinstance(raw, dict):
            return base
        for key in base:
            if key in raw:
                base[key] = raw[key]
        # 强制限制 supported 列表只保留合法档位且去重
        supported = base.get("supported_thinking_intensities") or []
        supported = [s for s in supported if s in THINKING_LEVELS]
        if not supported:
            supported = ["高"]
        base["supported_thinking_intensities"] = list(dict.fromkeys(supported))
        if base.get("default_thinking_intensity") not in THINKING_LEVELS:
            base["default_thinking_intensity"] = "高"
        # 数值字段兜底
        try:
            base["context_input"] = int(base.get("context_input") or 0)
        except (TypeError, ValueError):
            base["context_input"] = 0
        try:
            base["context_output"] = int(base.get("context_output") or 0)
        except (TypeError, ValueError):
            base["context_output"] = 0
        return base

    def _item_out(self, item: dict[str, Any], is_default: bool, include_key: bool) -> dict[str, Any]:
        """统一 list/get 返回的字段形态：剥离明文 key、补全 advanced。"""
        out = dict(item)
        out["advanced"] = self._normalize_advanced(out.get("advanced"))
        if include_key:
            return out
        if "api_key" in out:
            out["has_api_key"] = bool(out.get("api_key"))
            del out["api_key"]
        out["is_default"] = is_default
        return out

    def __init__(self, config_path: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        home = project_root / "home"
        self._path = config_path or (home / "config" / "models.json")
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            seed = self._seed_from_env()
            self._write({"models": [seed], "default_model_id": seed["id"]})

    def _seed_from_env(self) -> dict[str, Any]:
        """用 .env / 环境变量生成默认模型条目。"""
        return {
            "id": str(uuid.uuid4()),
            "name": os.getenv("VISIONAGENT_MODEL_NAME", "hy3"),
            "api_endpoint": os.getenv(
                "VISIONAGENT_API_ENDPOINT", "http://localhost:8111/v1"
            ),
            "api_key": os.getenv("VISIONAGENT_API_KEY", ""),
            "model_id": os.getenv("VISIONAGENT_MODEL_NAME", "hy3"),
            "advanced": default_advanced(),
        }

    def _read(self) -> dict[str, Any]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("invalid models.json")
            data.setdefault("models", [])
            data.setdefault("default_model_id", None)
            return data
        except Exception:
            seed = self._seed_from_env()
            data = {"models": [seed], "default_model_id": seed["id"]}
            self._write(data)
            return data

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self._path)

    def list_models(self, mask_key: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            models = []
            for m in data["models"]:
                if mask_key:
                    item = dict(m)
                    if item.get("api_key"):
                        key = item["api_key"]
                        item["api_key_masked"] = (
                            key[:4] + "****" + key[-2:] if len(key) > 6 else "****"
                        )
                        item["has_api_key"] = True
                        del item["api_key"]
                    else:
                        item["has_api_key"] = False
                    item["is_default"] = item.get("id") == data.get("default_model_id")
                    item["advanced"] = self._normalize_advanced(item.get("advanced"))
                    models.append(item)
                else:
                    models.append(self._item_out(m, m.get("id") == data.get("default_model_id"), include_key=True))
            return models

    def get_model(self, model_uid: str, include_key: bool = False) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            for m in data["models"]:
                if m.get("id") == model_uid:
                    if include_key:
                        item = dict(m)
                        item["advanced"] = self._normalize_advanced(item.get("advanced"))
                        return item
                    item = dict(m)
                    if "api_key" in item:
                        item["has_api_key"] = bool(item.get("api_key"))
                        del item["api_key"]
                    item["advanced"] = self._normalize_advanced(item.get("advanced"))
                    item["is_default"] = item.get("id") == data.get("default_model_id")
                    return item
            return None

    def get_default(self, include_key: bool = True) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            default_id = data.get("default_model_id")
            models = data.get("models") or []
            if not models:
                return None
            for m in models:
                if m.get("id") == default_id:
                    return self._item_out(m, True, include_key=include_key)
            return self._item_out(models[0], True, include_key=include_key)

    def create_model(
        self,
        name: str,
        api_endpoint: str,
        api_key: str,
        model_id: str,
        set_default: bool = False,
        advanced: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            item = {
                "id": str(uuid.uuid4()),
                "name": name.strip() or model_id.strip() or "model",
                "api_endpoint": api_endpoint.strip(),
                "api_key": api_key or "",
                "model_id": model_id.strip() or name.strip(),
                "advanced": self._normalize_advanced(advanced),
            }
            data["models"].append(item)
            if set_default or not data.get("default_model_id"):
                data["default_model_id"] = item["id"]
            self._write(data)
            out = dict(item)
            out.pop("api_key", None)
            out["has_api_key"] = bool(item.get("api_key"))
            out["is_default"] = item["id"] == data["default_model_id"]
            return out

    def update_model(
        self,
        model_uid: str,
        name: str | None = None,
        api_endpoint: str | None = None,
        api_key: str | None = None,
        model_id: str | None = None,
        set_default: bool | None = None,
        advanced: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            target = None
            for m in data["models"]:
                if m.get("id") == model_uid:
                    target = m
                    break
            if target is None:
                return None
            if name is not None:
                target["name"] = name.strip() or target.get("name", "model")
            if api_endpoint is not None:
                target["api_endpoint"] = api_endpoint.strip()
            if api_key is not None and api_key != "":
                # 空字符串表示不修改；传入新值才更新
                target["api_key"] = api_key
            if model_id is not None:
                target["model_id"] = model_id.strip() or target.get("model_id", "")
            if set_default:
                data["default_model_id"] = model_uid
            if advanced is not None:
                # 合并而非整体替换：保留未在请求里出现但已存在的字段
                target["advanced"] = self._normalize_advanced(
                    {**(target.get("advanced") or {}), **advanced}
                )
            self._write(data)
            out = dict(target)
            out.pop("api_key", None)
            out["has_api_key"] = bool(target.get("api_key"))
            out["is_default"] = target.get("id") == data.get("default_model_id")
            return out

    def delete_model(self, model_uid: str) -> bool:
        with self._lock:
            data = self._read()
            before = len(data["models"])
            data["models"] = [m for m in data["models"] if m.get("id") != model_uid]
            if len(data["models"]) == before:
                return False
            if data.get("default_model_id") == model_uid:
                data["default_model_id"] = (
                    data["models"][0]["id"] if data["models"] else None
                )
            self._write(data)
            return True

    def set_default(self, model_uid: str) -> bool:
        with self._lock:
            data = self._read()
            if not any(m.get("id") == model_uid for m in data["models"]):
                return False
            data["default_model_id"] = model_uid
            self._write(data)
            return True
