"""会话管理模块 - 负责会话的创建、读取、更新、删除与持久化存储。"""
import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any


class SessionManager:
    """会话管理器：管理会话元数据与消息，支持持久化到本地 JSON 文件。"""

    def __init__(self, storage_dir: str | None = None) -> None:
        # 默认存储路径：app/storage/sessions
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            storage_dir = os.path.join(base_dir, "app", "storage", "sessions")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        # 内存缓存
        self._conversations: dict[str, list[dict[str, Any]]] = {}
        self._titles: dict[str, str] = {}
        self._order: list[str] = []

        # 启动时从磁盘加载已有会话
        self._load_all()

    # ===== 持久化相关 =====
    def _session_file(self, conversation_id: str) -> Path:
        return self.storage_dir / f"{conversation_id}.json"

    def _load_all(self) -> None:
        """启动时加载所有会话文件。"""
        files = sorted(
            self.storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for file in files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cid = data.get("id")
                if not cid:
                    continue
                self._conversations[cid] = data.get("messages", [])
                self._titles[cid] = data.get("title", "新对话")
                self._order.append(cid)
            except Exception as e:
                print(f"加载会话文件失败 {file}: {e}")

    def _save(self, conversation_id: str) -> None:
        """将会话写入磁盘。"""
        data = {
            "id": conversation_id,
            "title": self._titles.get(conversation_id, "新对话"),
            "messages": self._conversations.get(conversation_id, []),
            "updated_at": time.time(),
        }
        with open(self._session_file(conversation_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ===== 会话 CRUD =====
    def create(self, title: str = "新对话") -> dict[str, str]:
        """创建新会话。"""
        with self._lock:
            cid = str(int(time.time() * 1000))
            self._conversations[cid] = []
            self._titles[cid] = title
            self._order.insert(0, cid)
            self._save(cid)
            return {"conversation_id": cid, "title": title}

    def list_all(self) -> list[dict[str, Any]]:
        """返回所有会话的列表（按最近更新时间倒序）。"""
        with self._lock:
            items: list[dict[str, Any]] = []
            for cid in self._order:
                msgs = self._conversations.get(cid, [])
                preview = ""
                for m in msgs:
                    if m.get("role") == "user":
                        preview = (m.get("content") or "")[:50]
                        break
                items.append(
                    {
                        "id": cid,
                        "title": self._titles.get(cid, "新对话"),
                        "preview": preview,
                        "message_count": len(msgs),
                    }
                )
            return items

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """获取指定会话的完整信息。"""
        with self._lock:
            if conversation_id not in self._conversations:
                return None
            return {
                "conversation_id": conversation_id,
                "title": self._titles.get(conversation_id, "新对话"),
                "messages": list(self._conversations[conversation_id]),
            }

    def delete(self, conversation_id: str) -> bool:
        """删除会话。"""
        with self._lock:
            if conversation_id not in self._conversations:
                return False
            del self._conversations[conversation_id]
            self._titles.pop(conversation_id, None)
            if conversation_id in self._order:
                self._order.remove(conversation_id)
            file = self._session_file(conversation_id)
            if file.exists():
                try:
                    file.unlink()
                except Exception as e:
                    print(f"删除会话文件失败 {file}: {e}")
            return True

    def rename(self, conversation_id: str, title: str) -> bool:
        """重命名会话。"""
        with self._lock:
            if conversation_id not in self._conversations:
                return False
            self._titles[conversation_id] = title
            self._save(conversation_id)
            return True

    def exists(self, conversation_id: str) -> bool:
        return conversation_id in self._conversations

    def add_message(self, conversation_id: str, role: str, content: str) -> bool:
        """向会话追加消息并持久化。"""
        with self._lock:
            if conversation_id not in self._conversations:
                return False
            self._conversations[conversation_id].append(
                {"role": role, "content": content}
            )
            self._save(conversation_id)
            # 更新顺序（最近活跃的排在最前）
            if conversation_id in self._order:
                self._order.remove(conversation_id)
            self._order.insert(0, conversation_id)
            return True

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取会话的所有消息。"""
        with self._lock:
            return list(self._conversations.get(conversation_id, []))
