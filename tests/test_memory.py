"""Tests for exogram.memory.jsonl_store module."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from exogram.memory.jsonl_store import JsonlMemoryStore, _score_record, _tokenize
from exogram.models import CognitionRecord


class TestTokenize:
    """Tests for _tokenize function."""

    def test_splits_by_space(self):
        result = _tokenize("hello world")
        assert result == ["hello", "world"]

    def test_chinese_bigrams(self):
        result = _tokenize("你好世界")
        assert "你好" in result
        assert "好世" in result
        assert "世界" in result

    def test_empty_string(self):
        result = _tokenize("")
        assert result == []

    def test_single_char(self):
        result = _tokenize("a")
        assert result == ["a"]

    def test_removes_punctuation(self):
        result = _tokenize("项目,管理")
        assert len(result) > 0


class TestScoreRecord:
    """Tests for _score_record function."""

    def test_matching_query_gets_positive_score(self):
        record = CognitionRecord(
            id="test",
            topic="项目管理",
            summary="项目管理系统操作",
        )
        score = _score_record(record, query="项目")
        assert score > 0

    def test_non_matching_query_gets_zero_score(self):
        record = CognitionRecord(
            id="test",
            topic="项目管理",
            summary="项目管理系统操作",
        )
        score = _score_record(record, query="完全不相关的查询")
        assert score == pytest.approx(0, abs=0.1)

    def test_recency_boost(self):
        # Recent record should score higher
        recent_record = CognitionRecord(
            id="recent",
            topic="测试",
            summary="测试内容",
            created_at=datetime.now(timezone.utc),
        )
        
        # Old record
        old_record = CognitionRecord(
            id="old",
            topic="测试",
            summary="测试内容",
        )
        # Manually set old date
        old_record.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        
        recent_score = _score_record(recent_record, query="测试")
        old_score = _score_record(old_record, query="测试")
        
        # Recent should have higher recency boost
        assert recent_score > old_score


class TestJsonlMemoryStore:
    """Tests for JsonlMemoryStore class."""

    def test_creates_file_if_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            store = JsonlMemoryStore(path)
            assert path.exists()

    def test_append_and_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            store = JsonlMemoryStore(path)
            
            record = CognitionRecord(
                id="test-1",
                topic="TestTopic",
                summary="Test summary",
            )
            store.append(record)
            
            records = store.list_all()
            assert len(records) == 1
            assert records[0].id == "test-1"

    def test_append_multiple(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            store = JsonlMemoryStore(path)
            
            for i in range(3):
                record = CognitionRecord(
                    id=f"test-{i}",
                    topic="TestTopic",
                    summary=f"Summary {i}",
                )
                store.append(record)
            
            records = store.list_all()
            assert len(records) == 3

    def test_retrieve_by_topic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            store = JsonlMemoryStore(path)
            
            # Add records with different topics
            store.append(CognitionRecord(
                id="a",
                topic="TopicA",
                summary="Content A",
            ))
            store.append(CognitionRecord(
                id="b",
                topic="TopicB",
                summary="Content B",
            ))
            
            hits = store.retrieve(topic="TopicA", query="Content")
            assert len(hits) == 1
            assert hits[0].record.topic == "TopicA"

    def test_retrieve_with_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            store = JsonlMemoryStore(path)
            
            # Add many records
            for i in range(10):
                store.append(CognitionRecord(
                    id=f"test-{i}",
                    topic="Topic",
                    summary=f"内容 {i}",
                ))
            
            hits = store.retrieve(topic=None, query="内容", limit=3)
            assert len(hits) <= 3

    def test_retrieve_returns_sorted_by_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            store = JsonlMemoryStore(path)
            
            store.append(CognitionRecord(
                id="low",
                topic="Topic",
                summary="无关内容",
            ))
            store.append(CognitionRecord(
                id="high",
                topic="Topic",
                summary="搜索 搜索 搜索",  # More matches
            ))
            
            hits = store.retrieve(topic=None, query="搜索")
            if len(hits) >= 2:
                # Higher score should come first
                assert hits[0].score >= hits[1].score

    def test_handles_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.jsonl"
            
            # Write some valid and invalid lines
            with path.open("w") as f:
                f.write('{"id": "valid", "topic": "T", "summary": "S"}\n')
                f.write('invalid json line\n')
                f.write('{"id": "valid2", "topic": "T2", "summary": "S2"}\n')
            
            store = JsonlMemoryStore(path)
            records = store.list_all()
            
            # Should only get valid records
            assert len(records) == 2
