from __future__ import annotations

from exogram.models_rich import RichCognitionRecord


class CognitiveContextManager:
    """
    负责将 RichCognitionRecord 转换为 LLM 可理解的 Prompt Context。
    相当于 Prompt Engineer 角色。
    """

    def __init__(self, record: RichCognitionRecord) -> None:
        self.record = record

    def build_system_instruction(self) -> str:
        """
        构建注入到 Agent 的系统级指令（长期记忆/锦囊妙计）。
        """
        parts = []

        # 1. 任务背景
        parts.append(f"【任务背景】\n你正在操作 {self.record.website.name} ({self.record.website.type})。")
        parts.append(f"目标：{self.record.task.goal}")
        parts.append("")

        # 2. 关键 UI 元素 (Known UI Elements)
        # 帮助 Agent 快速定位，减少盲目探索
        if self.record.key_elements:
            parts.append("【已知关键 UI 元素】")
            for elem in self.record.key_elements:
                parts.append(f"- [{elem.type}] {elem.name}: {elem.usage}")
            parts.append("")

        # 3. 操作知识 (Tips & Precautions)
        # 提取高价值的 Tips，避免踩坑
        knowledge = self.record.operation_knowledge
        has_knowledge = False
        
        knowledge_parts = []
        if knowledge.navigation_pattern:
            knowledge_parts.append(f"导航模式: {knowledge.navigation_pattern}")
        
        if knowledge.form_filling_tips:
            knowledge_parts.append("表单填写技巧:")
            for tip in knowledge.form_filling_tips:
                knowledge_parts.append(f"- {tip}")
        
        if knowledge.precautions:
            knowledge_parts.append("注意事项 (Precautions):")
            for warn in knowledge.precautions:
                knowledge_parts.append(f"- ⚠️ {warn}")

        if knowledge_parts:
            parts.append("【操作锦囊 (SOP)】")
            parts.extend(knowledge_parts)
            parts.append("")

        # 4. 复制指南 (Replication Guide) - 总体流程概览
        if self.record.replication_guide:
            parts.append("【参考流程】")
            parts.append(self.record.replication_guide)
            parts.append("")

        return "\n".join(parts)
