from __future__ import annotations

import json
import re
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


_WS_RE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    s = s.strip()
    s = _WS_RE.sub(" ", s)
    return s


def safe_preview_value(value: str | None, limit: int = 80) -> str | None:
    if value is None:
        return None
    v = normalize_text(value)
    if len(v) > limit:
        return v[:limit] + "…"
    return v
