from __future__ import annotations

from exogram.models_rich import RichCognitionRecord

SAFE_MODE_INSTRUCTION = (
    "\n\n【安全模式 — 重要规则】\n"
    "在执行任务前，请先判断任务类型：\n"
    "1. 查询/只读任务（如查看、搜索、查询、导出数据、查找信息）：正常完成全部操作并返回结果。\n"
    "2. 写入/修改任务（如创建、新建、编辑、修改、删除、提交、发布、审批）：\n"
    "   - 请导航到目标操作页面\n"
    "   - 如有表单，可以帮助定位到相关区域\n"
    "   - 但【绝对不要】点击最终的「提交」「创建」「确认」「删除」「发布」等执行按钮\n"
    "   - 到达目标位置后，停止操作并在最终输出中说明：已导航到目标页面，请用户自行完成最终操作\n"
)


def build_agent_task(
    *,
    task: str,
    wisdom: str = "",
    start_url: str | None = None,
    safe_mode: bool = True,
) -> str:
    """将用户任务、认知指导、起始 URL、安全模式指令拼装为最终 Agent 任务字符串。"""
    parts: list[str] = []

    if start_url:
        parts.append(f"首先打开网址: {start_url}")

    parts.append(task.strip())

    if wisdom:
        parts.append(f"\n【认知指导】\n{wisdom}")

    if safe_mode:
        parts.append(SAFE_MODE_INSTRUCTION)

    return "\n\n".join(parts)


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
        parts: list[str] = []

        parts.append(f"【任务背景】\n你正在操作 {self.record.website.name} ({self.record.website.type})。")
        parts.append(f"目标：{self.record.task.goal}")
        parts.append("")

        if self.record.key_elements:
            parts.append("【已知关键 UI 元素】")
            for elem in self.record.key_elements:
                parts.append(f"- [{elem.type}] {elem.name}: {elem.usage}")
            parts.append("")

        knowledge = self.record.operation_knowledge
        knowledge_parts: list[str] = []
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

        if self.record.replication_guide:
            parts.append("【参考流程】")
            parts.append(self.record.replication_guide)
            parts.append("")

        return "\n".join(parts)
