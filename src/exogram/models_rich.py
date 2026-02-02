from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebsiteInfo(BaseModel):
    name: str
    url: str | None = None  # 网站入口 URL
    type: str
    description: str


class TaskInfo(BaseModel):
    summary: str
    goal: str
    steps_count: int


class OperationPhase(BaseModel):
    phase: str
    description: str
    key_actions: list[str]


class KeyElement(BaseModel):
    name: str
    type: str
    usage: str


class OperationKnowledge(BaseModel):
    navigation_pattern: str
    form_filling_tips: list[str] = Field(default_factory=list)
    common_workflows: list[str] = Field(default_factory=list)
    precautions: list[str] = Field(default_factory=list)


class MetaInfo(BaseModel):
    id: str
    topic: str
    created_at: datetime
    source: str
    steps_count: int
    start_url: str | None = None  # 录制时的起始 URL


class RichCognitionRecord(BaseModel):
    website: WebsiteInfo
    task: TaskInfo
    operation_flow: list[OperationPhase]
    key_elements: list[KeyElement]
    operation_knowledge: OperationKnowledge
    replication_guide: str
    meta: MetaInfo = Field(alias="_meta")
