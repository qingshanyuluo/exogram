from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

try:
    from browser_use import Agent, Browser
    from browser_use.llm import ChatOpenAI
except ImportError:
    # Allow running without browser_use installed (e.g. for context verification)
    Agent = None
    Browser = None
    ChatOpenAI = None

from exogram.execution.auth import get_cdp_compatible_auth_file
from exogram.utils import get_logger

logger = get_logger("Executor")


@dataclass(frozen=True)
class RunResult:
    injected_wisdom: str
    history: object


class Executor:
    """基于认知执行任务的执行器"""
    
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

    async def run(self, *, task: str, wisdom: str | None = None) -> RunResult:
        wisdom = (wisdom or "").strip()
        
        # 构建带认知的任务
        full_task = task.strip()
        if wisdom:
            full_task = f"{task.strip()}\n\n【认知指导】\n{wisdom}\n"

        # 配置浏览器
        browser_kwargs = {
            "headless": False,
            "disable_security": True,
            "enable_default_extensions": False,
        }
        
        # 自动加载认证状态
        if self.start_url:
            auth_file = get_cdp_compatible_auth_file(self.start_url)
            if auth_file:
                browser_kwargs["storage_state"] = auth_file
                logger.info("已加载认证状态")
            full_task = f"首先打开网址: {self.start_url}\n\n{full_task}"
        
        browser = Browser(**browser_kwargs)
        llm = ChatOpenAI(
            model=self.model,
            api_key=self.openai_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=self.openai_base_url,
            timeout=self.openai_timeout,
            max_retries=self.openai_max_retries,
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
        )
        agent = Agent(task=full_task, llm=llm, browser=browser)
        history = await agent.run()
        return RunResult(injected_wisdom=wisdom, history=history)

    def run_sync(self, *, task: str, wisdom: str | None = None) -> RunResult:
        return asyncio.run(self.run(task=task, wisdom=wisdom))
