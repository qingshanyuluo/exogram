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
from exogram.execution.context import build_agent_task
from exogram.utils import get_logger

logger = get_logger("Executor")

DEBUG_TIMING = os.getenv("EXOGRAM_DEBUG_TIMING", "0") == "1"
FLASH_MODE = os.getenv("EXOGRAM_FLASH_MODE", "0") == "1"


def _log_timing(label: str, start: float) -> None:
    elapsed = time.time() - start
    logger.info(f"⏱️ {label}: {elapsed:.2f}s")


@dataclass(frozen=True)
class RunResult:
    injected_wisdom: str
    history: object


class Executor:
    """基于认知执行任务的执行器，支持持久浏览器会话。

    职责：管理 Browser / LLM 生命周期，驱动 browser-use Agent 执行。
    不包含终端交互逻辑（见 session.InteractiveSession）。
    """

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
        wisdom: str = "",
        navigate_to_start: bool = True,
        safe_mode: bool = True,
    ) -> RunResult:
        total_start = time.time()

        full_task = build_agent_task(
            task=task,
            wisdom=wisdom,
            start_url=self.start_url if navigate_to_start else None,
            safe_mode=safe_mode,
        )

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
    # 生命周期
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.kill()
            self._browser = None

    def run_sync(self, *, task: str, wisdom: str = "") -> RunResult:
        """单次执行后关闭浏览器（向后兼容）。"""
        async def _run_and_close() -> RunResult:
            try:
                return await self.run(task=task, wisdom=wisdom, safe_mode=False)
            finally:
                await self.close()
        return asyncio.run(_run_and_close())
