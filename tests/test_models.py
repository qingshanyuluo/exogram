"""Tests for exogram.models module."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from exogram.models import (
    CognitionRecord,
    RawStep,
    RawStepsDocument,
    RetrievalHit,
)


class TestRawStep:
    """Tests for RawStep model."""

    def test_minimal_step(self):
        step = RawStep(idx=0, action="click")
        assert step.idx == 0
        assert step.action == "click"
        assert step.url is None
        assert step.meta == {}

    def test_full_step(self):
        step = RawStep(
            idx=1,
            action="type",
            url="https://example.com",
            target_text="Submit",
            target_role="button",
            target_label="提交按钮",
            value="hello",
            meta={"testId": "submit-btn"},
        )
        assert step.idx == 1
        assert step.action == "type"
        assert step.url == "https://example.com"
        assert step.value == "hello"
        assert step.meta["testId"] == "submit-btn"


class TestRawStepsDocument:
    """Tests for RawStepsDocument model."""

    def test_creates_with_steps(self):
        doc = RawStepsDocument(
            topic="TestTopic",
            source="test-source",
            steps=[
                RawStep(idx=0, action="navigate", url="https://example.com"),
                RawStep(idx=1, action="click", target_text="Login"),
            ],
        )
        assert doc.topic == "TestTopic"
        assert doc.source == "test-source"
        assert len(doc.steps) == 2
        assert doc.created_at is not None

    def test_default_created_at(self):
        doc = RawStepsDocument(topic="Test", source="test", steps=[])
        assert doc.created_at is not None
        # Should be close to now (within 1 minute)
        now = datetime.now(timezone.utc)
        delta = abs((now - doc.created_at).total_seconds())
        assert delta < 60


class TestCognitionRecord:
    """Tests for CognitionRecord model."""

    def test_minimal_record(self):
        record = CognitionRecord(
            id="test-id",
            topic="TestTopic",
            summary="Test summary",
        )
        assert record.id == "test-id"
        assert record.topic == "TestTopic"
        assert record.summary == "Test summary"
        assert record.task_tags == []
        assert record.preference_rules == []

    def test_full_record(self):
        record = CognitionRecord(
            id="test-id",
            topic="TestTopic",
            summary="Test summary",
            task_tags=["tag1", "tag2"],
            key_path_features=["feature1"],
            preference_rules=["rule1"],
            exception_handling=["exception1"],
            anti_patterns=["anti1"],
        )
        assert len(record.task_tags) == 2
        assert "tag1" in record.task_tags


class TestRetrievalHit:
    """Tests for RetrievalHit model."""

    def test_creates_hit(self):
        record = CognitionRecord(
            id="test-id",
            topic="TestTopic",
            summary="Test summary",
        )
        hit = RetrievalHit(record=record, score=0.85)
        assert hit.record.id == "test-id"
        assert hit.score == 0.85
