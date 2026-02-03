from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class RawStep(BaseModel):
    idx: int
    action: str = Field(description="抽象动作类型（click/type/navigate/wait/...）")
    url: str | None = None
    target_text: str | None = Field(default=None, description="用户可见的按钮/链接/标签文本（尽量语义化）")
    target_role: str | None = Field(default=None, description="aria role/语义角色（如 button, link, input）")
    target_label: str | None = Field(default=None, description="input 的 label/placeholder/name 等（尽量语义化）")
    selector_hint: str | None = Field(default=None, description="可选：弱提示。MVP 默认尽量不依赖")
    value: str | None = Field(default=None, description="输入值（会做脱敏/截断）")
    wait_ms: int | None = None
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class RawStepsDocument(BaseModel):
    topic: str
    source: str = Field(description="录制来源描述（例如 workflow-use export）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: list[RawStep]


class CognitionRecord(BaseModel):
    id: str
    topic: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_recording: str | None = None
    task_tags: list[str] = Field(default_factory=list)
    key_path_features: list[str] = Field(default_factory=list)
    preference_rules: list[str] = Field(default_factory=list)
    exception_handling: list[str] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)
    summary: str
    raw_llm_output: str | None = None


class RetrievalHit(BaseModel):
    record: CognitionRecord
    score: float


# ========== 语义蒸馏相关模型 ==========


class CleanedStep(BaseModel):
    """清洗后的步骤（供 browser-use 类比操作使用）"""

    action: str = Field(description="动作类型：click/type/navigate/select/wait")
    target: str = Field(description="语义化的目标描述，如'点击提交按钮'而非 selector")
    value: str | None = Field(default=None, description="输入值或选择值")
    precondition: str | None = Field(default=None, description="执行此步骤的前置条件")
    expected_result: str | None = Field(default=None, description="预期结果或状态变化")


class StepSegment(BaseModel):
    """操作步骤分段"""

    segment_id: int = Field(description="段落序号，从 0 开始")
    intent: str = Field(description="段落意图，如'导航到项目页面'")
    start_idx: int = Field(description="起始步骤索引")
    end_idx: int = Field(description="结束步骤索引（包含）")
    page_context: dict[str, Any] | None = Field(default=None, description="页面快照/上下文")
    summary: str = Field(description="段落摘要")
    cleaned_steps: list[CleanedStep] = Field(default_factory=list, description="清洗后的步骤")


class SemanticRecord(BaseModel):
    """语义理解结果（总分总蒸馏产出）"""

    id: str
    topic: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_recording: str | None = None

    # 总：整体理解
    website_description: str = Field(description="网站/系统描述")
    task_summary: str = Field(description="任务总结（用户做了什么）")
    task_goal: str | None = Field(default=None, description="推测的任务目标")

    # 分：分段理解
    segments: list[StepSegment] = Field(default_factory=list, description="操作分段")

    # 总：汇总的可复用知识
    task_tags: list[str] = Field(default_factory=list, description="任务标签")
    key_path_features: list[str] = Field(default_factory=list, description="关键路径特征")
    preference_rules: list[str] = Field(default_factory=list, description="偏好规则")
    exception_handling: list[str] = Field(default_factory=list, description="异常处理经验")
    anti_patterns: list[str] = Field(default_factory=list, description="反模式提醒")

    # 元数据
    raw_llm_output: str | None = None


class SemanticRetrievalHit(BaseModel):
    """语义记录检索结果"""

    record: SemanticRecord
    score: float


MemoryFormat = Literal["jsonl"]
