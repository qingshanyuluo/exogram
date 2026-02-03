from __future__ import annotations

import json
import logging
import re
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    获取一个配置好的 logger 实例。
    
    日志格式：[模块名] 消息
    默认日志级别：INFO
    
    可通过设置环境变量 EXOGRAM_LOG_LEVEL 来调整日志级别。
    """
    import os
    
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(name)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # 从环境变量读取日志级别
        level_name = os.getenv("EXOGRAM_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)
    
    return logger


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
