"""logs - one shared live log used by the pipeline and surfaced by the
dashboard. Keeps a ring buffer in memory and appends to a session file.

A progress callback can be registered so the dashboard receives structured
stage / percent / message updates without the pipeline knowing about HTTP.
"""

import threading
import time
from collections import deque

from . import settings

_LOCK = threading.Lock()
_LINES = deque(maxlen=1200)
_CALLBACK = None
_FILE = None


def set_callback(fn):
    """fn(event: dict) receives every structured update."""
    global _CALLBACK
    _CALLBACK = fn


def _emit(event: dict):
    if _CALLBACK:
        try:
            _CALLBACK(event)
        except Exception:
            pass


def start_session(name: str = "session"):
    global _FILE
    settings.ensure_dirs()
    _FILE = settings.LOG_DIR / f"{name}.log"
    with _LOCK:
        _LINES.clear()


def log(message: str, level: str = "info"):
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    with _LOCK:
        _LINES.append({"t": stamp, "level": level, "msg": message})
        if _FILE:
            try:
                with open(_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
    _emit({"type": "log", "level": level, "message": message})


def stage(index: int, total: int, name: str):
    log(f"STAGE {index}/{total}: {name}", "stage")
    _emit({"type": "stage", "index": index, "total": total, "name": name})


def progress(percent: float, detail: str = ""):
    _emit({"type": "progress", "percent": round(percent, 1),
           "detail": detail})


def metric(key: str, value):
    _emit({"type": "metric", "key": key, "value": value})


def lines(limit: int = 300):
    with _LOCK:
        return list(_LINES)[-limit:]


def export_text() -> str:
    with _LOCK:
        return "\n".join(f"[{l['t']}] {l['msg']}" for l in _LINES)
