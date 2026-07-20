"""热更新模块：后端 reload + 前端文件监听自动刷新。

用法：
    from app.api.debug import enable_hot_reload

    enable_hot_reload(app)   # 注册热更新路由 + 启动文件监听
"""
import hashlib
import os
import threading
import time
import urllib.request

from fastapi import FastAPI


# ===== 热更新状态 =====
_should_reload = False
_stop_watch: threading.Event | None = None
_watcher_thread: threading.Thread | None = None


def enable_hot_reload(app: FastAPI) -> None:
    """启用热更新：注册路由 + 启动前端文件监听。"""
    _register_routes(app)
    _start_frontend_watcher()


def disable_hot_reload() -> None:
    """停止热更新（窗口关闭时调用）。"""
    global _stop_watch, _watcher_thread
    if _stop_watch is not None:
        _stop_watch.set()
    _watcher_thread = None


def _register_routes(app: FastAPI) -> None:
    @app.get("/api/reload-frontend")
    async def reload_frontend():
        """前端文件变更后通知浏览器刷新。"""
        global _should_reload
        _should_reload = True
        return {"ok": True}

    @app.get("/api/poll-reload")
    async def poll_reload():
        """前端轮询检测是否需要刷新。"""
        global _should_reload
        if _should_reload:
            _should_reload = False
            return {"reload": True}
        return {"reload": False}


def _start_frontend_watcher() -> None:
    """启动前端文件监听线程。"""
    global _stop_watch, _watcher_thread
    _stop_watch = threading.Event()
    _watcher_thread = threading.Thread(
        target=_watch_frontend, args=(_stop_watch,), daemon=True
    )
    _watcher_thread.start()


def _watch_frontend(stop_event: threading.Event) -> None:
    """监听前端文件变更，通知浏览器刷新。"""
    static_dir_abs = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app", "static"
    )
    checksums = {}

    def _hash_file(path):
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return None

    # 初始快照
    for root, _dirs, files in os.walk(static_dir_abs):
        for f in files:
            fpath = os.path.join(root, f)
            checksums[fpath] = _hash_file(fpath)

    while not stop_event.is_set():
        time.sleep(0.5)
        for root, _dirs, files in os.walk(static_dir_abs):
            for f in files:
                fpath = os.path.join(root, f)
                new_hash = _hash_file(fpath)
                if checksums.get(fpath) != new_hash:
                    checksums[fpath] = new_hash
                    try:
                        urllib.request.urlopen(
                            "http://127.0.0.1:8000/api/reload-frontend", timeout=1
                        )
                    except Exception:
                        pass
                    break
