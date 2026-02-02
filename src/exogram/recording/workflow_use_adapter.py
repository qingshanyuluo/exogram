from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from exogram.models import RawStep, RawStepsDocument
from exogram.utils import normalize_text, safe_preview_value


class WorkflowUseJsonAdapter:
    """
    把 workflow-use 导出的 *.workflow.json 归一化为 RawStepsDocument。

    设计目标：
    - 最大化“可迁移的认知信息”（可见文本、语义角色、动作类型、异常/等待）
    - 最小化“脆弱的定位信息”（CSS/XPath）——仅作为弱 hint
    - 对未知 schema 尽量容错（不同版本字段可能变化）
    """

    def __init__(self) -> None:
        pass

    def load(self, path: Path, *, topic: str) -> RawStepsDocument:
        data = json.loads(path.read_text(encoding="utf-8"))
        steps = self._extract_steps(data)
        raw_steps: list[RawStep] = []
        for idx, step in enumerate(steps):
            raw_steps.append(self._normalize_step(idx, step))

        return RawStepsDocument(
            topic=topic,
            source=f"workflow-use:{path.name}",
            steps=raw_steps,
        )

    def _extract_steps(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        # 常见结构：{"steps":[...]} / {"workflow":{"steps":[...]}} / {"workflowDefinition":{"steps":[...]}}
        for key in ("steps",):
            if isinstance(data.get(key), list):
                return data[key]

        for parent_key in ("workflow", "workflowDefinition", "definition"):
            parent = data.get(parent_key)
            if isinstance(parent, dict) and isinstance(parent.get("steps"), list):
                return parent["steps"]

        # 容错：递归找第一个 list[dict] 且 dict 里包含 action/type 字段
        found = self._find_step_list(data)
        if found is not None:
            return found

        raise ValueError("无法在 workflow JSON 中找到 steps 列表（schema 不匹配）。")

    def _find_step_list(self, obj: Any) -> list[dict[str, Any]] | None:
        if isinstance(obj, list):
            if obj and all(isinstance(x, dict) for x in obj):
                if any(("action" in x or "type" in x or "op" in x) for x in obj):
                    return obj  # type: ignore[return-value]
            for x in obj:
                found = self._find_step_list(x)
                if found is not None:
                    return found
            return None

        if isinstance(obj, dict):
            for v in obj.values():
                found = self._find_step_list(v)
                if found is not None:
                    return found
            return None

        return None

    def _normalize_step(self, idx: int, step: dict[str, Any]) -> RawStep:
        action = (
            step.get("action")
            or step.get("type")
            or step.get("op")
            or step.get("name")
            or "unknown"
        )
        action = str(action)

        url = step.get("url") or step.get("href") or step.get("pageUrl")
        if isinstance(url, str):
            url = normalize_text(url)
        else:
            url = None

        target_text = self._pick_first_str(
            step,
            [
                "text",
                "visibleText",
                "label",
                "ariaLabel",
                "name",
                "title",
                "buttonText",
                "linkText",
            ],
        )

        target_role = self._pick_first_str(step, ["role", "ariaRole", "elementRole"])
        target_label = self._pick_first_str(step, ["placeholder", "inputLabel", "fieldLabel"])

        selector_hint = self._pick_first_str(step, ["selector", "css", "xpath", "selectorHint"])
        if selector_hint:
            selector_hint = safe_preview_value(selector_hint, limit=120)

        value = self._pick_first_str(step, ["value", "input", "typedText", "textToType"])
        value = safe_preview_value(value, limit=80)

        wait_ms = self._pick_first_int(step, ["waitMs", "timeoutMs", "delayMs"])
        error = self._pick_first_str(step, ["error", "exception", "message"])

        # 保留少量 meta，方便后续演进；但避免塞入整段 DOM/截图 base64
        meta: dict[str, Any] = {}
        for k in ("strategy", "confidence", "retries", "note"):
            if k in step:
                meta[k] = step[k]

        return RawStep(
            idx=idx,
            action=action,
            url=url,
            target_text=target_text,
            target_role=target_role,
            target_label=target_label,
            selector_hint=selector_hint,
            value=value,
            wait_ms=wait_ms,
            error=error,
            meta=meta,
        )

    def _pick_first_str(self, step: dict[str, Any], keys: list[str]) -> str | None:
        for k in keys:
            v = step.get(k)
            if isinstance(v, str) and v.strip():
                return normalize_text(v)
        return None

    def _pick_first_int(self, step: dict[str, Any], keys: list[str]) -> int | None:
        for k in keys:
            v = step.get(k)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
        return None
