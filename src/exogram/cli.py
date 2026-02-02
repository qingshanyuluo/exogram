from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

from exogram.config import load_settings
# 注：Distiller 是旧版蒸馏器，目前使用 SemanticDistiller
from exogram.execution import Executor
from exogram.memory import JsonlMemoryStore
from exogram.models import RawStepsDocument
from exogram.recording import WorkflowUseJsonAdapter
from exogram.utils import ensure_dir, read_json, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode="markdown")


def _resolve_data_paths(data_dir: Path) -> dict[str, Path]:
    return {
        "recordings_dir": data_dir / "recordings",
        "memory_dir": data_dir / "memory",
        "runs_dir": data_dir / "runs",
        "memory_jsonl": data_dir / "memory" / "memory.jsonl",
    }


@app.command()
def record(
    topic: str = typer.Option(..., "--topic", help="场景/主题，例如 ERP_Export"),
    workflow_json: Path = typer.Option(..., "--workflow-json", exists=True, dir_okay=False, help="workflow-use 导出的 .workflow.json 路径"),
    out: Path | None = typer.Option(None, "--out", help="输出 RawSteps JSON 路径（默认写到 data/recordings/{topic}.raw_steps.json）"),
) -> None:
    """
    录制导入：把 workflow-use 的 .workflow.json 归一化为 RawStepsDocument（去 selector 化）。
    """
    load_dotenv()
    settings = load_settings()
    paths = _resolve_data_paths(settings.data_dir)
    ensure_dir(paths["recordings_dir"])

    adapter = WorkflowUseJsonAdapter()
    doc = adapter.load(workflow_json, topic=topic)

    out_path = out or (paths["recordings_dir"] / f"{topic}.raw_steps.json")
    write_json(out_path, doc.model_dump(mode="json"))
    typer.echo(f"已写入 RawSteps: {out_path}")


@app.command("record-live")
def record_live(
    topic: str = typer.Option(..., "--topic", help="场景/主题，例如 ERP_Export"),
    start_url: str = typer.Option("https://example.com", "--start-url", help="打开浏览器后的初始地址（也可手动在地址栏输入）"),
    out: Path | None = typer.Option(None, "--out", help="输出 RawSteps JSON 路径（默认写到 data/recordings/{topic}.raw_steps.json）"),
    storage_state: Path | None = typer.Option(None, "--storage-state", help="登录态文件路径（默认 ~/.exogram/auth/{domain}.json）"),
    no_save_storage: bool = typer.Option(False, "--no-save-storage", help="录制结束后不保存登录态"),
    auth_domain: str | None = typer.Option(None, "--auth-domain", help="用于命名登录态文件的域名（默认从 start_url 提取）"),
) -> None:
    """
    交互式录制：打开浏览器让你操作，页面右上角有"结束录制"悬浮按钮，点击后输出 RawSteps JSON。

    **新特性：支持 SSO 登录态复用**
    - 首次录制会自动保存登录态到 ~/.exogram/auth/{domain}.json
    - 后续录制会自动加载已保存的登录态，跳过重复登录
    - 使用 --no-save-storage 禁止保存登录态
    - 使用 --storage-state 指定自定义登录态文件路径

    **增强录制信息**
    - 自动识别 Ant Design / Element UI 等组件（tree/select/table 等）
    - 采集 data-testid、CSS selector、组件类型等稳定定位信息
    - 便于 browser-use 等框架复用

    依赖：
    - pip install -e ".[recorder]"（或 pip install playwright）
    - playwright install chromium
    """
    load_dotenv()
    settings = load_settings()
    paths = _resolve_data_paths(settings.data_dir)
    ensure_dir(paths["recordings_dir"])

    out_path = out or (paths["recordings_dir"] / f"{topic}.raw_steps.json")

    from exogram.recording import LiveRecorder

    try:
        recorder = LiveRecorder()
        written = recorder.record(
            topic=topic,
            start_url=start_url,
            out_path=out_path,
            storage_state_path=storage_state,
            save_storage_state=not no_save_storage,
            auth_domain=auth_domain,
        )
    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(code=2) from e

    typer.echo(f"已写入 RawSteps: {written}")


@app.command("setup-auth")
def setup_auth(
    start_url: str = typer.Option(..., "--start-url", help="SSO 登录页地址"),
    storage_state: Path | None = typer.Option(None, "--storage-state", help="登录态保存路径（默认 ~/.exogram/auth/{domain}.json）"),
    auth_domain: str | None = typer.Option(None, "--auth-domain", help="用于命名登录态文件的域名（默认从 start_url 提取）"),
) -> None:
    """
    登录态初始化：打开浏览器让你手动登录（如扫码），登录成功后关闭窗口即可保存登录态。

    **使用场景**
    - 首次使用前，先运行此命令完成 SSO 登录
    - 登录态过期后，重新运行此命令刷新

    **示例**

        # 初始化 hellobike SSO 登录态
        exogram setup-auth --start-url https://sso2.hellobike.cn/

        # 后续录制时自动复用登录态
        exogram record-live --topic Demo --start-url https://metis2.hellobike.cn/campaign

    依赖：
    - pip install -e ".[recorder]"（或 pip install playwright）
    - playwright install chromium
    """
    load_dotenv()

    from exogram.recording import LiveRecorder

    try:
        saved_path = LiveRecorder.setup_auth(
            start_url=start_url,
            storage_state_path=storage_state,
            auth_domain=auth_domain,
        )
        typer.secho(f"登录态已保存: {saved_path}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(code=2) from e


@app.command()
def distill(
    recording: Path = typer.Option(..., "--recording", exists=True, dir_okay=False, help="RawSteps JSON（由 exogram record 生成）"),
    out: Path | None = typer.Option(None, "--out", help="输出认知文档路径（默认替换 .raw_steps.json 为 .cognition.json）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="输出详细日志"),
) -> None:
    """
    语义蒸馏：分析录制的操作步骤，生成完整的操作认知文档。

    生成的认知文档包含：
    - 网站描述（名称、类型、功能）
    - 任务摘要和目标
    - 操作流程（分阶段描述）
    - 关键元素及使用方法
    - 操作知识（导航模式、表单填写技巧、常见工作流、注意事项）
    - AI Agent 复现指南

    **示例**

        exogram distill --recording data/recordings/DemoLive.raw_steps.json
        exogram distill --recording demo.json --out demo.cognition.json -v
    """
    load_dotenv()
    settings = load_settings()

    raw_obj = read_json(recording)
    raw_doc = RawStepsDocument.model_validate(raw_obj)

    # 确定输出路径
    if out:
        out_path = out
    else:
        out_path = recording.with_suffix("").with_suffix(".cognition.json")
        if str(recording).endswith(".raw_steps.json"):
            out_path = Path(str(recording).replace(".raw_steps.json", ".cognition.json"))

    # 使用语义蒸馏器
    from exogram.distillation.semantic_distiller import SemanticDistiller

    api_key = os.getenv("DISTILLATION_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DISTILLATION_OPENAI_BASE_URL") or settings.openai_base_url
    model = os.getenv("DISTILLATION_MODEL") or settings.distill_model

    if verbose:
        typer.echo(f"模型: {model}")
        typer.echo(f"API: {base_url}")

    try:
        distiller = SemanticDistiller(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=settings.llm_temperature,
        )
        result = distiller.distill(raw_doc, verbose=verbose)
    except Exception as e:
        typer.secho(f"蒸馏失败: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    # 保存结果（不含原始 LLM 输出）
    import json
    clean_result = {k: v for k, v in result.items() if not k.startswith("_raw")}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(clean_result, ensure_ascii=False, indent=2), encoding="utf-8")

    typer.secho(f"已生成操作认知: {out_path}", fg=typer.colors.GREEN)
    typer.echo(f"- 网站: {result.get('website', {}).get('name', '未知')}")
    typer.echo(f"- 任务: {result.get('task', {}).get('summary', '未知')}")
    typer.echo(f"- 操作阶段: {len(result.get('operation_flow', []))} 个")
    typer.echo(f"- 关键元素: {len(result.get('key_elements', []))} 个")


@app.command()
def memorize(
    cognition: Path = typer.Option(..., "--cognition", exists=True, dir_okay=False, help="cognition.json 文件路径"),
    memory_jsonl: Path | None = typer.Option(None, "--memory", help="记忆库路径（默认 data/memory/memory.jsonl）"),
) -> None:
    """
    记忆：将认知文档导入到长期记忆库。

    **示例**

        exogram memorize --cognition data/recordings/DemoLive.cognition.json
    """
    load_dotenv()
    settings = load_settings()
    paths = _resolve_data_paths(settings.data_dir)
    
    mem_path = memory_jsonl or paths["memory_jsonl"]
    
    # 读取 cognition.json
    cog_data = read_json(cognition)
    
    # 转换为 CognitionRecord 格式
    from exogram.models import CognitionRecord
    
    # 从 RichCognitionRecord 格式提取字段
    topic = cog_data.get("_meta", {}).get("topic", cognition.stem)
    record = CognitionRecord(
        id=cog_data.get("_meta", {}).get("id", str(uuid.uuid4())),
        topic=topic,
        created_at=datetime.fromisoformat(cog_data.get("_meta", {}).get("created_at", datetime.utcnow().isoformat())),
        source_recording=cog_data.get("_meta", {}).get("source"),
        task_tags=[cog_data.get("task", {}).get("summary", "")],
        key_path_features=[el.get("name", "") for el in cog_data.get("key_elements", [])],
        preference_rules=[tip for tip in cog_data.get("operational_knowledge", {}).get("form_tips", [])],
        exception_handling=[p for p in cog_data.get("operational_knowledge", {}).get("precautions", [])],
        anti_patterns=[],
        summary=cog_data.get("task", {}).get("goal", "") or cog_data.get("website", {}).get("description", ""),
    )
    
    # 追加到记忆库
    store = JsonlMemoryStore(mem_path)
    store.append(record)
    
    typer.secho(f"✓ 已将 '{topic}' 导入记忆库: {mem_path}", fg=typer.colors.GREEN)


def _format_wisdom(hits: list[tuple[float, dict[str, Any]]]) -> str:
    chunks: list[str] = []
    for score, obj in hits:
        created_at = obj.get("created_at", "")
        chunks.append(f"### 命中(score={score:.3f}, created_at={created_at})")
        for _k, title in [
            ("key_path_features", "关键路径特征"),
            ("preference_rules", "偏好规则"),
            ("exception_handling", "异常处理经验"),
            ("anti_patterns", "反模式/噪声提醒"),
        ]:
            items = obj.get(_k) or []
            if not items:
                continue
            chunks.append(f"- {title}:")
            for it in items:
                chunks.append(f"  - {it}")
    return "\n".join(chunks).strip()


@app.command()
def run(
    task: str = typer.Option(..., "--task", help="用户任务"),
    topic: str | None = typer.Option(None, "--topic", help="topic 名称（自动查找 data/recordings/{topic}.cognition.json）"),
    cognition: Path | None = typer.Option(None, "--cognition", exists=True, dir_okay=False, help="直接指定 cognition.json 文件"),
    model: str | None = typer.Option(None, "--model", help="执行模型"),
) -> None:
    """
    基于认知执行任务：加载认知 -> 注入 prompt -> browser-use Agent 执行。

    **示例**

        exogram run --topic DemoLive --task "帮我新建一个需求"
        exogram run --cognition demo.cognition.json --task "帮我新建一个需求"
    """
    load_dotenv()
    settings = load_settings()
    paths = _resolve_data_paths(settings.data_dir)
    ensure_dir(paths["runs_dir"])

    # 确定 cognition 文件路径
    cog_path: Path | None = cognition
    if not cog_path and topic:
        # 自动查找 topic 对应的 cognition 文件
        cog_path = paths["recordings_dir"] / f"{topic}.cognition.json"
        if not cog_path.exists():
            typer.secho(f"❌ 未找到认知文件: {cog_path}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    
    if not cog_path:
        typer.secho("❌ 请指定 --topic 或 --cognition", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # 加载认知
    from exogram.models_rich import RichCognitionRecord
    from exogram.execution.context import CognitiveContextManager
    
    typer.echo(f"📂 加载认知: {cog_path}")
    cog_data = json.loads(cog_path.read_text(encoding="utf-8"))
    record = RichCognitionRecord.model_validate(cog_data)
    
    # 提取 start_url
    start_url = record.website.url or record.meta.start_url
    if start_url:
        typer.echo(f"✓ 起始 URL: {start_url}")
    
    # 构建 wisdom
    context_manager = CognitiveContextManager(record)
    wisdom = context_manager.build_system_instruction()
    typer.echo(f"✓ 已加载 {len(record.key_elements)} 个 UI 元素")
    typer.echo(f"✓ 生成 {len(wisdom)} 字符认知指导")

    # 执行
    typer.echo(f"\n🚀 开始执行任务...")
    executor = Executor(
        model=model or settings.agent_model,
        openai_api_key=os.getenv("EXECUTION_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("EXECUTION_OPENAI_BASE_URL") or settings.openai_base_url,
        openai_timeout=settings.openai_timeout,
        openai_max_retries=settings.openai_max_retries,
        temperature=settings.llm_temperature,
        max_completion_tokens=settings.llm_max_tokens,
        start_url=start_url,
    )
    result = executor.run_sync(task=task, wisdom=wisdom)
    
    typer.secho("✅ 执行完成!", fg=typer.colors.GREEN)


def _safe_serialize_history(history: object) -> Any:
    # 尽量把 history 转成 JSON 友好结构；不行就退化为 str
    for attr in ("model_dump", "dict"):
        fn = getattr(history, attr, None)
        if callable(fn):
            try:
                return fn()  # type: ignore[misc]
            except Exception:
                pass

    to_json = getattr(history, "to_json", None)
    if callable(to_json):
        try:
            return json.loads(to_json())  # type: ignore[misc]
        except Exception:
            pass

    try:
        return json.loads(str(history))
    except Exception:
        return str(history)


if __name__ == "__main__":
    app()
