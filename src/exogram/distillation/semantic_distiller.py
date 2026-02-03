"""
语义蒸馏器 - 简化版

一次性调用 LLM，生成完整的操作认知描述，供后续 browser-use 类比操作。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from exogram.models import RawStepsDocument
from exogram.models_rich import (
    KeyElement,
    MetaInfo,
    OperationKnowledge,
    OperationPhase,
    RichCognitionRecord,
    TaskInfo,
    WebsiteInfo,
)
from exogram.utils import get_logger

logger = get_logger("Distill")


# ========== Prompt 模板 ==========

SYSTEM_PROMPT = """你是一名"浏览器操作分析师"。你的任务是分析用户在网页上的操作序列，生成一份完整的操作认知文档。

这份文档将用于指导 AI Agent（如 browser-use）在类似网站上执行类似任务。

【重要约束】
- 不要输出任何代码
- 不要依赖 CSS selector 或 XPath
- 用自然语言描述，让另一个 AI Agent 能够理解并复现
- 输出必须是 JSON 格式"""

USER_PROMPT = """请分析以下浏览器操作记录，生成完整的操作认知文档：

【主题】{topic}

【网站信息】
{website_info}

【操作步骤摘要】
{steps_summary}

【详细步骤】
{steps_detail}

---

请输出 JSON 格式的操作认知文档：
{{
  "website": {{
    "name": "网站/系统名称",
    "url": "网站入口URL（从操作记录中提取的第一个访问地址）",
    "type": "网站类型（如：项目管理系统、电商平台、OA系统等）",
    "description": "网站功能描述（2-3句话）"
  }},
  "task": {{
    "summary": "用户完成了什么任务（1句话）",
    "goal": "推测的任务目标",
    "steps_count": 操作步骤数
  }},
  "operation_flow": [
    {{
      "phase": "阶段名称（如：导航定位、查看详情、填写表单、提交确认）",
      "description": "这个阶段做了什么",
      "key_actions": ["关键操作1", "关键操作2"]
    }}
  ],
  "key_elements": [
    {{
      "name": "元素名称（如：项目树、需求表格、导入变更按钮）",
      "type": "元素类型（如：树形控件、表格、按钮、下拉框）",
      "usage": "如何使用这个元素"
    }}
  ],
  "operation_knowledge": {{
    "navigation_pattern": "导航模式描述（如何从首页到达目标页面）",
    "form_filling_tips": ["表单填写技巧"],
    "common_workflows": ["常见工作流程"],
    "precautions": ["注意事项"]
  }},
  "replication_guide": "如果 AI Agent 要执行类似任务，应该如何操作（3-5句话的指导）"
}}"""

PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", USER_PROMPT),
])


# ========== 辅助函数 ==========

def _extract_start_url(steps: list[dict]) -> str | None:
    """从步骤中提取起始 URL（第一个 navigate 动作的 URL）"""
    for step in steps:
        action = step.get("action", "")
        if action == "navigate":
            url = step.get("url", "")
            if url and url != "about:blank":
                return url
    # 备选：从 page_snapshot 中提取
    for step in steps:
        meta = step.get("meta", {})
        snapshot = meta.get("page_snapshot")
        if snapshot:
            url = snapshot.get("url", "")
            if url and url != "about:blank":
                return url
    return None


def _format_website_info(steps: list[dict]) -> str:
    """提取网站信息"""
    # 找第一个有 page_snapshot 的步骤
    for step in steps:
        meta = step.get("meta", {})
        snapshot = meta.get("page_snapshot")
        if snapshot:
            title = snapshot.get("title", "未知")
            url = snapshot.get("url", "")
            elements = snapshot.get("interactiveElements", [])
            
            # 提取菜单/导航信息
            menu_items = []
            for elem in elements[:20]:
                role = elem.get("role", "")
                text = elem.get("text", "")
                if role == "menuitem" and text and len(text) < 20:
                    menu_items.append(text)
            
            lines = [
                f"标题: {title}",
                f"URL: {url}",
            ]
            if menu_items:
                lines.append(f"主菜单: {', '.join(menu_items[:8])}")
            return "\n".join(lines)
    
    # 没有 snapshot，从 URL 提取
    for step in steps:
        url = step.get("url", "")
        if url and url != "about:blank":
            return f"URL: {url}"
    return "(无网站信息)"


def _format_steps_summary(steps: list[dict]) -> str:
    """生成步骤摘要"""
    actions = {"navigate": 0, "click": 0, "type": 0}
    urls = set()
    
    for step in steps:
        action = step.get("action", "")
        if action in actions:
            actions[action] += 1
        url = step.get("url", "")
        if url:
            # 提取路径部分
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path or "/"
            urls.add(f"{parsed.netloc}{path}")
    
    lines = [
        f"总步骤数: {len(steps)}",
        f"页面导航: {actions['navigate']} 次",
        f"点击操作: {actions['click']} 次",
        f"输入操作: {actions['type']} 次",
        f"访问页面: {', '.join(list(urls)[:5])}",
    ]
    return "\n".join(lines)


def _format_steps_detail(steps: list[dict], max_steps: int = 30) -> str:
    """格式化详细步骤"""
    lines = []
    
    for step in steps[:max_steps]:
        idx = step.get("idx", 0)
        action = step.get("action", "unknown")
        
        if action == "navigate":
            url = step.get("url", "")
            lines.append(f"[{idx}] 导航到: {url}")
        
        elif action == "click":
            target = step.get("target_text") or step.get("target_label") or ""
            if len(target) > 50:
                target = target[:50] + "..."
            
            # 添加组件类型信息
            meta = step.get("meta", {})
            comp_type = meta.get("componentType", "")
            tree_node = meta.get("treeNode")
            selected_option = meta.get("selectedOption")
            
            desc = f"[{idx}] 点击: {target}"
            if comp_type:
                desc += f" ({comp_type})"
            if tree_node and tree_node.get("title"):
                desc += f" [树节点: {tree_node['title']}]"
            if selected_option:
                desc += f" [选择: {selected_option.get('value', '')}]"
            lines.append(desc)
        
        elif action == "type":
            label = step.get("target_label") or "(输入框)"
            value = step.get("value", "")
            lines.append(f"[{idx}] 输入 {label}: {value}")
    
    if len(steps) > max_steps:
        lines.append(f"... 还有 {len(steps) - max_steps} 个步骤")
    
    return "\n".join(lines)


# ========== 主类 ==========

class SemanticDistiller:
    """语义蒸馏器"""
    
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.0,
    ):
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=4096,
        )
    
    def distill(
        self,
        raw: RawStepsDocument,
        *,
        verbose: bool = False,
    ) -> RichCognitionRecord:
        """
        执行语义蒸馏，生成操作认知文档。
        
        Args:
            raw: 原始操作步骤文档
            verbose: 是否输出详细日志
            
        Returns:
            RichCognitionRecord 类型化的操作认知文档
            
        Raises:
            ValueError: 如果 LLM 输出无法解析为有效的 JSON
            ValidationError: 如果解析后的数据不符合 RichCognitionRecord 模型
        """
        steps = [s.model_dump(mode="json") for s in raw.steps]
        
        if verbose:
            logger.info(f"分析 {len(steps)} 个操作步骤...")
        
        # 构建 prompt 输入
        prompt_input = {
            "topic": raw.topic,
            "website_info": _format_website_info(steps),
            "steps_summary": _format_steps_summary(steps),
            "steps_detail": _format_steps_detail(steps),
        }
        
        # 调用 LLM
        chain = PROMPT | self.llm
        response = chain.invoke(prompt_input)
        raw_output = response.content
        
        if verbose:
            logger.info(f"LLM 返回 {len(raw_output)} 字符")
        
        # 解析 JSON
        result = self._parse_json(raw_output)
        
        # 检查解析错误
        if "_error" in result:
            raise ValueError(f"LLM 输出解析失败: {result.get('_error')}. 原始输出: {result.get('_raw', '')[:500]}")
        
        # 提取起始 URL
        start_url = _extract_start_url(steps)
        
        # 如果 LLM 没有输出 website.url，从 start_url 补充
        if "website" in result and isinstance(result["website"], dict):
            if not result["website"].get("url") and start_url:
                result["website"]["url"] = start_url
        
        # 构建元数据
        result["_meta"] = {
            "id": str(uuid.uuid4()),
            "topic": raw.topic,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": raw.source,
            "steps_count": len(steps),
            "start_url": start_url,
        }
        
        # 验证并返回类型化的记录
        return RichCognitionRecord.model_validate(result)
    
    def _parse_json(self, text: str) -> dict:
        """解析 LLM 输出的 JSON"""
        t = text.strip()
        
        # 提取 JSON 块
        if "```json" in t:
            start = t.find("```json") + 7
            end = t.find("```", start)
            if end > start:
                t = t[start:end].strip()
        elif "```" in t:
            start = t.find("```") + 3
            end = t.find("```", start)
            if end > start:
                t = t[start:end].strip()
        
        # 找 JSON 对象
        if not t.startswith("{"):
            start = t.find("{")
            end = t.rfind("}") + 1
            if start >= 0 and end > start:
                t = t[start:end]
        
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return {"_error": "JSON 解析失败", "_raw": text}


def distill_recording(
    recording_path: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "gpt-4o",
    verbose: bool = False,
) -> RichCognitionRecord:
    """
    便捷函数：蒸馏录制文件。
    
    Args:
        recording_path: RawSteps JSON 文件路径
        api_key: OpenAI API Key
        base_url: API 基础 URL
        model: 模型名称
        verbose: 是否输出详细日志
        
    Returns:
        RichCognitionRecord 类型化的操作认知文档
    """
    import os
    from pathlib import Path
    
    # 读取录制文件
    path = Path(recording_path)
    raw_obj = json.loads(path.read_text(encoding="utf-8"))
    raw_doc = RawStepsDocument.model_validate(raw_obj)
    
    # 创建蒸馏器
    distiller = SemanticDistiller(
        api_key=api_key or os.getenv("OPENAI_API_KEY"),
        base_url=base_url,
        model=model,
    )
    
    return distiller.distill(raw_doc, verbose=verbose)
