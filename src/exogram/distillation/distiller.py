from __future__ import annotations

import json
import uuid
from datetime import datetime

from openai import APIStatusError, OpenAI

from exogram.models import CognitionRecord, RawStepsDocument
from exogram.utils import normalize_text


class Distiller:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None,
        timeout: float,
        max_retries: int,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    def distill(self, *, topic: str, raw: RawStepsDocument, source_recording: str | None = None) -> CognitionRecord:
        prompt = _build_distillation_prompt(topic=topic, raw_steps=raw.model_dump(mode="json"))

        text = ""
        # 优先使用 Responses API（OpenAI 官方）；若兼容网关不支持 /responses，则回退到 /chat/completions
        try:
            resp = self.client.responses.create(
                model=self.model,
                input=prompt,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
            text = (resp.output_text or "").strip()
        except APIStatusError as e:
            if e.status_code in (404, 405):
                cc = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                text = ((cc.choices[0].message.content or "") if cc.choices else "").strip()
            else:
                raise
        if not text:
            raise RuntimeError("LLM 未返回可用文本（output_text 为空）。")

        parsed = _parse_structured(text)

        record = CognitionRecord(
            id=str(uuid.uuid4()),
            topic=topic,
            created_at=datetime.utcnow(),
            source_recording=source_recording,
            task_tags=parsed.get("task_tags", []),
            key_path_features=parsed.get("key_path_features", []),
            preference_rules=parsed.get("preference_rules", []),
            exception_handling=parsed.get("exception_handling", []),
            anti_patterns=parsed.get("anti_patterns", []),
            summary=parsed.get("summary", normalize_text(text)[:8000]),
            raw_llm_output=text,
        )
        return record


def _build_distillation_prompt(*, topic: str, raw_steps: dict) -> str:
    """
    强约束：不要输出代码；不要依赖 CSS selector；提炼“决策逻辑/操作策略/异常经验”。
    """
    raw_json = json.dumps(raw_steps, ensure_ascii=False, indent=2)
    return f"""
你是一名“流程复盘分析师”。下面是用户在浏览器中的操作日志（已结构化）。请你提炼可迁移的“系统认知/操作策略”，用于指导未来的智能 Agent。

【重要约束】
- 不要输出任何可执行代码（不要 Python/JS）。
- 不要依赖具体 CSS/XPath/DOM 细节；如果出现 selector，只能作为弱背景，不可写成关键规则。
- 重点提炼：用户为什么这么点/这么选？在找什么信号？忽略了什么？遇到异常怎么自救？
- 输出必须尽量短、可复用、可注入到 system prompt。

【输入】
主题(topic)：{topic}
操作日志(raw_steps)：
{raw_json}

【输出格式】请严格输出为 JSON（只输出 JSON，不要其他文本），字段如下：
{{
  "summary": "1-3 句总结（面向未来 agent）",
  "task_tags": ["可选：3-8 个标签，中文短语"],
  "key_path_features": ["关键路径特征，3-10 条"],
  "preference_rules": ["偏好规则，3-10 条"],
  "exception_handling": ["异常处理经验，2-8 条"],
  "anti_patterns": ["噪声/反模式提醒（不要做什么），0-5 条"]
}}
""".strip()


def _parse_structured(text: str) -> dict:
    # 期望 LLM 直接输出 JSON；若包了一层 ```json 也容错
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        # 可能是 ```json\n{...}\n```
        t = t.replace("json\n", "", 1).strip()

    try:
        obj = json.loads(t)
    except Exception:
        # 最差兜底：把全文当 summary
        return {"summary": normalize_text(text)}

    if not isinstance(obj, dict):
        return {"summary": normalize_text(text)}

    # 清洗列表字段
    for k in ("task_tags", "key_path_features", "preference_rules", "exception_handling", "anti_patterns"):
        v = obj.get(k, [])
        if isinstance(v, list):
            obj[k] = [normalize_text(str(x)) for x in v if str(x).strip()]
        else:
            obj[k] = []

    s = obj.get("summary")
    if not isinstance(s, str) or not s.strip():
        obj["summary"] = normalize_text(text)[:2000]
    else:
        obj["summary"] = normalize_text(s)

    return obj
