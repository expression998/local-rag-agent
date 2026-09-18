"""供应商运行时配置：API Key、接口地址、动态模型列表。

保存在本机 provider_settings.json（已 gitignore，绝不能提交——内含明文密钥），
Web 界面配置后对 CLI 同样生效。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(__file__).parent / "provider_settings.json"
_ALLOWED_FIELDS = {"api_key", "base_url", "models"}
_lock = threading.Lock()


def load() -> dict[str, dict[str, Any]]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save(settings: dict[str, dict[str, Any]]) -> None:
    with _lock:
        SETTINGS_PATH.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def get(name: str) -> dict[str, Any]:
    """读取某个供应商的运行时覆盖项；无配置或结构非法时返回空 dict。

    空字符串/空列表视为无覆盖（不遮蔽 .env 静态配置）。
    """
    entry = load().get(name)
    if not isinstance(entry, dict):
        return {}
    return {k: v for k, v in entry.items() if k in _ALLOWED_FIELDS and v}


def update(name: str, **fields: Any) -> dict[str, Any]:
    settings = load()
    entry = settings.setdefault(name, {})
    for key, value in fields.items():
        if key in _ALLOWED_FIELDS and value is not None:
            entry[key] = value
    save(settings)
    return entry


def clear(name: str) -> None:
    settings = load()
    settings.pop(name, None)
    save(settings)
