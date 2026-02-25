from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

try:
    from browser_use import Agent, Browser
    from browser_use.llm import ChatOpenAI
except ImportError:
    Agent = None
    Browser = None
    ChatOpenAI = None

from exogram.execution.auth import get_cdp_compatible_auth_file
from exogram.utils import get_logger

logger = get_logger("Executor")

DEBUG_TIMING = os.getenv("EXOGRAM_DEBUG_TIMING", "0") == "1"
FLASH_MODE = os.getenv("EXOGRAM_FLASH_MODE", "0") == "1"

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


def _log_timing(label: str, start: float) -> None:
    elapsed = time.time() - start
    logger.info(f"⏱️ {label}: {elapsed:.2f}s")


@dataclass(frozen=True)
class RunResult:
    injected_wisdom: str
    history: object


class Executor:
    """基于认知执行任务的执行器，支持持久浏览器会话和交互式循环。"""

    def __init__(
        self,
        *,
        model: str,
        openai_api_key: str | None,
        openai_base_url: str | None,
        openai_timeout: float,
        openai_max_retries: int,
        temperature: float,
        max_completion_tokens: int,
        start_url: str | None = None,
    ) -> None:
        self.model = model
        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.openai_timeout = openai_timeout
        self.openai_max_retries = openai_max_retries
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.start_url = start_url

        self._browser: Browser | None = None
        self._llm: ChatOpenAI | None = None

    # ------------------------------------------------------------------
    # 懒加载 Browser / LLM（整个交互会话中只创建一次）
    # ------------------------------------------------------------------

    def _ensure_browser(self) -> Browser:
        if self._browser is not None:
            return self._browser

        browser_kwargs: dict = {
            "headless": False,
            "disable_security": True,
            "enable_default_extensions": False,
            "keep_alive": True,
        }

        if DEBUG_TIMING:
            browser_kwargs["minimum_wait_page_load_time"] = 0.1
            browser_kwargs["wait_for_network_idle_page_load_time"] = 0.3
            browser_kwargs["wait_between_actions"] = 0.3
            logger.info("🔧 调试模式：已减少等待时间")

        if self.start_url:
            auth_file = get_cdp_compatible_auth_file(self.start_url)
            if auth_file:
                browser_kwargs["storage_state"] = auth_file
                logger.info("已加载认证状态")

        t0 = time.time()
        self._browser = Browser(**browser_kwargs)
        if DEBUG_TIMING:
            _log_timing("Browser 对象创建", t0)

        return self._browser

    def _ensure_llm(self) -> ChatOpenAI:
        if self._llm is not None:
            return self._llm

        is_deepseek = self.openai_base_url and "deepseek.com" in self.openai_base_url
        self._llm = ChatOpenAI(
            model=self.model,
            api_key=self.openai_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=self.openai_base_url,
            timeout=self.openai_timeout,
            max_retries=self.openai_max_retries,
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
            dont_force_structured_output=bool(is_deepseek),
            add_schema_to_system_prompt=bool(is_deepseek),
        )
        return self._llm

    # ------------------------------------------------------------------
    # 核心执行
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        task: str,
        wisdom: str | None = None,
        navigate_to_start: bool = True,
        safe_mode: bool = True,
    ) -> RunResult:
        total_start = time.time()
        wisdom = (wisdom or "").strip()

        full_task = task.strip()
        if wisdom:
            full_task = f"{task.strip()}\n\n【认知指导】\n{wisdom}\n"

        if navigate_to_start and self.start_url:
            full_task = f"首先打开网址: {self.start_url}\n\n{full_task}"

        if safe_mode:
            full_task += SAFE_MODE_INSTRUCTION

        browser = self._ensure_browser()
        llm = self._ensure_llm()

        agent_kwargs: dict = {"task": full_task, "llm": llm, "browser": browser}
        if FLASH_MODE:
            agent_kwargs["flash_mode"] = True
            agent_kwargs["max_history_items"] = 10
            agent_kwargs["max_actions_per_step"] = 4
            logger.info("⚡ Flash 模式已启用（性能优化）")

        agent = Agent(**agent_kwargs)

        step_count = 0
        step_start_time = time.time()

        async def on_step_start(agent_instance):
            nonlocal step_start_time
            step_start_time = time.time()

        async def on_step_end(agent_instance):
            nonlocal step_count, step_start_time
            step_count += 1
            if DEBUG_TIMING:
                logger.info(f"⏱️ Step {step_count} 耗时: {time.time() - step_start_time:.2f}s")

        logger.info("🚀 Agent 开始执行...")
        history = await agent.run(on_step_start=on_step_start, on_step_end=on_step_end)

        if DEBUG_TIMING:
            _log_timing("Agent.run() 总耗时", total_start)
            logger.info(f"📊 总步数: {step_count}")

        return RunResult(injected_wisdom=wisdom, history=history)

    # ------------------------------------------------------------------
    # 交互式会话：任务完成后留在终端等待新任务
    # ------------------------------------------------------------------

    async def interactive_run(
        self,
        *,
        task: str,
        wisdom: str | None = None,
        safe_mode: bool = True,
    ) -> None:
        """执行首个任务，然后进入交互循环，等待用户输入新任务。"""
        try:
            await self.run(
                task=task, wisdom=wisdom,
                navigate_to_start=True, safe_mode=safe_mode,
            )
        except Exception as e:
            logger.error(f"❌ 任务执行出错: {e}")

        _print_interactive_banner()

        loop = asyncio.get_running_loop()
        while True:
            try:
                user_input: str = await loop.run_in_executor(
                    None, input, "📝 请输入新任务 (quit 退出): ",
                )
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            logger.info("📡 正在获取当前页面状态…")
            try:
                await self.run(
                    task=user_input, wisdom=wisdom,
                    navigate_to_start=False, safe_mode=safe_mode,
                )
                print("\n✅ 任务执行完成！继续输入新任务或 quit 退出。\n")
            except Exception as e:
                logger.error(f"❌ 任务执行出错: {e}")
                print("⚠️ 执行出错，浏览器保持打开。你可以继续输入新任务。\n")

        print("\n🔄 正在关闭浏览器...")
        await self.close()
        print("👋 已退出。")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.kill()
            self._browser = None

    def run_interactive_sync(
        self, *, task: str, wisdom: str | None = None, safe_mode: bool = True,
    ) -> None:
        asyncio.run(
            self.interactive_run(task=task, wisdom=wisdom, safe_mode=safe_mode),
        )

    def run_sync(self, *, task: str, wisdom: str | None = None) -> RunResult:
        """单次执行后关闭浏览器（向后兼容）。"""
        async def _run_and_close() -> RunResult:
            try:
                return await self.run(task=task, wisdom=wisdom, safe_mode=False)
            finally:
                await self.close()
        return asyncio.run(_run_and_close())


def _print_interactive_banner() -> None:
    print("\n" + "=" * 60)
    print("✅ 任务执行完成！浏览器保持打开。")
    print("💡 你可以在浏览器中手动操作，也可以在下方输入新任务。")
    print("   输入 quit / exit / q 退出程序并关闭浏览器。")
    print("=" * 60 + "\n")
