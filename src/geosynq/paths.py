from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Return the repository root from inside the src layout."""
    return Path(__file__).resolve().parents[2]


def resolve_project_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return project_root() / p
