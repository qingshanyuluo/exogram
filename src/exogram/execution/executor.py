from __future__ import annotations

import asyncio
import os
import time
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

# 调试：启用详细计时日志
DEBUG_TIMING = os.getenv("EXOGRAM_DEBUG_TIMING", "0") == "1"

# 性能优化：启用 flash_mode（跳过评估、目标、思考，只用 memory）
FLASH_MODE = os.getenv("EXOGRAM_FLASH_MODE", "0") == "1"


def _log_timing(label: str, start: float) -> None:
    """输出计时日志"""
    elapsed = time.time() - start
    logger.info(f"⏱️ {label}: {elapsed:.2f}s")


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
        total_start = time.time()
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
        

        # 调试：减少等待时间
        if DEBUG_TIMING:
            browser_kwargs["minimum_wait_page_load_time"] = 0.1
            browser_kwargs["wait_for_network_idle_page_load_time"] = 0.3
            browser_kwargs["wait_between_actions"] = 0.3
            logger.info("🔧 调试模式：已减少等待时间")
        
        # 自动加载认证状态
        t0 = time.time()
        if self.start_url:
            auth_file = get_cdp_compatible_auth_file(self.start_url)
            if auth_file:
                browser_kwargs["storage_state"] = auth_file
                logger.info("已加载认证状态")
            full_task = f"首先打开网址: {self.start_url}\n\n{full_task}"
        if DEBUG_TIMING:
            _log_timing("认证文件加载", t0)
        
        # 启动浏览器
        t0 = time.time()
        browser = Browser(**browser_kwargs)
        if DEBUG_TIMING:
            _log_timing("Browser对象创建", t0)
        
        # DeepSeek 官方 API 不支持 structured output，需要禁用
        # 同时将 schema 加入 system prompt 以提高格式正确率
        is_deepseek = self.openai_base_url and "deepseek.com" in self.openai_base_url
        llm = ChatOpenAI(
            model=self.model,
            api_key=self.openai_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=self.openai_base_url,
            timeout=self.openai_timeout,
            max_retries=self.openai_max_retries,
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
            dont_force_structured_output=is_deepseek,
            add_schema_to_system_prompt=is_deepseek,
        )
        
        # 创建 Agent（性能优化参数）
        agent_kwargs = {
            "task": full_task,
            "llm": llm,
            "browser": browser,
        }
        
        if FLASH_MODE:
            agent_kwargs["flash_mode"] = True           # 跳过评估、目标、思考，只用 memory
            agent_kwargs["max_history_items"] = 10      # 只保留最近 10 步历史（最小值要求 > 5）
            agent_kwargs["max_actions_per_step"] = 4    # 每步最多 4 个动作
            logger.info("⚡ Flash 模式已启用（性能优化）")
        
        agent = Agent(**agent_kwargs)
        
        # 创建步骤计时回调
        step_count = 0
        step_start_time = time.time()
        
        async def on_step_start(agent_instance):
            nonlocal step_start_time
            step_start_time = time.time()
        
        async def on_step_end(agent_instance):
            nonlocal step_count, step_start_time
            step_count += 1
            elapsed = time.time() - step_start_time
            if DEBUG_TIMING:
                logger.info(f"⏱️ Step {step_count} 耗时: {elapsed:.2f}s")
        
        # 运行 Agent
        t0 = time.time()
        logger.info("🚀 Agent 开始执行...")
        history = await agent.run(on_step_start=on_step_start, on_step_end=on_step_end)
        if DEBUG_TIMING:
            _log_timing("Agent.run() 总耗时", t0)
            _log_timing("整体执行总耗时", total_start)
            logger.info(f"📊 总步数: {step_count}")
        
        return RunResult(injected_wisdom=wisdom, history=history)

    def run_sync(self, *, task: str, wisdom: str | None = None) -> RunResult:
        return asyncio.run(self.run(task=task, wisdom=wisdom))
