from __future__ import annotations

import os
from pathlib import Path

from .paths import project_root


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env(path: str | Path | None = None) -> dict[str, str]:
    """Load a simple .env file into os.environ without external dependencies."""
    env_path = Path(path) if path else project_root() / ".env"
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded

    text = env_path.read_text(encoding="utf-8-sig")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" in line:
            key, value = line.split("=", 1)
        elif "：" in line:
            key, value = line.split("：", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip()
        value = _strip_quotes(value)
        if not key:
            continue
        loaded[key] = value
        os.environ.setdefault(key, value)
        os.environ.setdefault(key.upper(), value)
    return loaded


def first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    lowered = {key.lower(): value for key, value in os.environ.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return default


def redact(value: str | None, keep: int = 4) -> str:
    if not value:
        return "<missing>"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"
