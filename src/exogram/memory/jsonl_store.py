from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

from exogram.models import CognitionRecord, RetrievalHit
from exogram.utils import ensure_dir, normalize_text


class JsonlMemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        ensure_dir(self.path.parent)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(self, record: CognitionRecord) -> None:
        line = record.model_dump_json(ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def list_all(self) -> list[CognitionRecord]:
        if not self.path.exists():
            return []
        records: list[CognitionRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                records.append(CognitionRecord.model_validate(obj))
            except Exception:
                # 允许坏行存在（手工编辑/旧版本）
                continue
        return records

    def retrieve(self, *, topic: str | None, query: str, limit: int = 5) -> list[RetrievalHit]:
        records = self.list_all()
        hits: list[RetrievalHit] = []
        for r in records:
            if topic and r.topic != topic:
                continue
            score = _score_record(r, query=query)
            if score <= 0:
                continue
            hits.append(RetrievalHit(record=r, score=score))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


_NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(query: str) -> list[str]:
    q = normalize_text(query)
    # 如果有空格，按空格拆；否则对中文/无空格场景用 2-gram
    if " " in q:
        parts = [p for p in q.split(" ") if p]
        return parts

    q2 = _NON_WORD.sub("", q)
    if len(q2) <= 2:
        return [q2] if q2 else []

    grams = [q2[i : i + 2] for i in range(len(q2) - 1)]
    # 去重但保持顺序
    seen: set[str] = set()
    out: list[str] = []
    for g in grams:
        if g and g not in seen:
            out.append(g)
            seen.add(g)
    return out


def _score_record(record: CognitionRecord, *, query: str) -> float:
    tokens = _tokenize(query)
    if not tokens:
        return 0.0

    blob = "\n".join(
        [
            record.topic,
            " ".join(record.task_tags),
            " ".join(record.key_path_features),
            " ".join(record.preference_rules),
            " ".join(record.exception_handling),
            record.summary,
        ]
    ).lower()

    score = 0.0
    for t in tokens:
        tl = t.lower()
        if not tl:
            continue
        if tl in blob:
            score += 1.0

    # 新近性加成（轻微）：越新越高
    age_days = (datetime.utcnow() - record.created_at).total_seconds() / 86400.0
    recency_boost = 1.0 / (1.0 + max(age_days, 0.0) / 30.0)  # 30 天半衰
    return score * (0.7 + 0.3 * recency_boost) + 0.01 * math.log(1 + len(blob))
