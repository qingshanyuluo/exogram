"""Tests for exogram.models_rich module."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from exogram.models_rich import (
    KeyElement,
    MetaInfo,
    OperationKnowledge,
    OperationPhase,
    RichCognitionRecord,
    TaskInfo,
    WebsiteInfo,
)


class TestWebsiteInfo:
    """Tests for WebsiteInfo model."""

    def test_creates_website_info(self):
        info = WebsiteInfo(
            name="Test Site",
            url="https://example.com",
            type="电商平台",
            description="测试网站描述",
        )
        assert info.name == "Test Site"
        assert info.url == "https://example.com"
        assert info.type == "电商平台"

    def test_url_is_optional(self):
        info = WebsiteInfo(
            name="Test Site",
            type="内部系统",
            description="内部系统描述",
        )
        assert info.url is None


class TestOperationKnowledge:
    """Tests for OperationKnowledge model."""

    def test_minimal_knowledge(self):
        knowledge = OperationKnowledge(
            navigation_pattern="从首页进入",
        )
        assert knowledge.navigation_pattern == "从首页进入"
        assert knowledge.form_filling_tips == []
        assert knowledge.precautions == []

    def test_full_knowledge(self):
        knowledge = OperationKnowledge(
            navigation_pattern="从首页进入",
            form_filling_tips=["先填写必填项"],
            common_workflows=["流程1"],
            precautions=["注意事项1"],
        )
        assert len(knowledge.form_filling_tips) == 1
        assert len(knowledge.precautions) == 1


class TestRichCognitionRecord:
    """Tests for RichCognitionRecord model."""

    def test_creates_from_dict(self):
        data = {
            "website": {
                "name": "测试系统",
                "url": "https://test.com",
                "type": "项目管理系统",
                "description": "项目管理描述",
            },
            "task": {
                "summary": "完成了登录操作",
                "goal": "登录系统",
                "steps_count": 5,
            },
            "operation_flow": [
                {
                    "phase": "登录阶段",
                    "description": "输入用户名密码",
                    "key_actions": ["输入用户名", "输入密码", "点击登录"],
                }
            ],
            "key_elements": [
                {
                    "name": "登录按钮",
                    "type": "按钮",
                    "usage": "点击进行登录",
                }
            ],
            "operation_knowledge": {
                "navigation_pattern": "直接访问登录页",
                "form_filling_tips": ["先输入用户名"],
                "common_workflows": [],
                "precautions": ["注意密码大小写"],
            },
            "replication_guide": "访问登录页，输入凭据，点击登录。",
            "_meta": {
                "id": "test-id",
                "topic": "Login",
                "created_at": "2024-01-01T00:00:00+00:00",
                "source": "test-source",
                "steps_count": 5,
                "start_url": "https://test.com/login",
            },
        }

        record = RichCognitionRecord.model_validate(data)
        
        assert record.website.name == "测试系统"
        assert record.task.summary == "完成了登录操作"
        assert len(record.operation_flow) == 1
        assert record.operation_flow[0].phase == "登录阶段"
        assert len(record.key_elements) == 1
        assert record.operation_knowledge.navigation_pattern == "直接访问登录页"
        assert record.meta.id == "test-id"
        assert record.meta.start_url == "https://test.com/login"

    def test_serializes_with_alias(self):
        data = {
            "website": {
                "name": "测试",
                "type": "测试",
                "description": "测试",
            },
            "task": {
                "summary": "测试",
                "goal": "测试",
                "steps_count": 1,
            },
            "operation_flow": [],
            "key_elements": [],
            "operation_knowledge": {
                "navigation_pattern": "测试",
            },
            "replication_guide": "测试",
            "_meta": {
                "id": "test",
                "topic": "test",
                "created_at": "2024-01-01T00:00:00+00:00",
                "source": "test",
                "steps_count": 1,
            },
        }

        record = RichCognitionRecord.model_validate(data)
        dumped = record.model_dump(by_alias=True)
        
        # Should use _meta alias instead of meta
        assert "_meta" in dumped
        assert "meta" not in dumped
