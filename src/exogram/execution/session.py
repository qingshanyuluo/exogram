from __future__ import annotations

import asyncio

from exogram.execution.executor import Executor
from exogram.utils import get_logger

logger = get_logger("Session")


class InteractiveSession:
    """交互式会话：执行首个任务后保持浏览器打开，在终端等待用户输入新任务。

    用户在等待期间可以直接在浏览器中手动操作，
    输入新任务后 Agent 会重新扫描当前页面状态再执行。
    """

    def __init__(
        self,
        executor: Executor,
        *,
        wisdom: str = "",
        safe_mode: bool = True,
    ) -> None:
        self._executor = executor
        self._wisdom = wisdom
        self._safe_mode = safe_mode

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def start(self, initial_task: str) -> None:
        """同步入口：执行首个任务并进入交互循环。"""
        asyncio.run(self._loop(initial_task))

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _loop(self, initial_task: str) -> None:
        try:
            await self._executor.run(
                task=initial_task,
                wisdom=self._wisdom,
                navigate_to_start=True,
                safe_mode=self._safe_mode,
            )
        except Exception as e:
            logger.error(f"❌ 任务执行出错: {e}")

        _print_banner()

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
                await self._executor.run(
                    task=user_input,
                    wisdom=self._wisdom,
                    navigate_to_start=False,
                    safe_mode=self._safe_mode,
                )
                print("\n✅ 任务执行完成！继续输入新任务或 quit 退出。\n")
            except Exception as e:
                logger.error(f"❌ 任务执行出错: {e}")
                print("⚠️ 执行出错，浏览器保持打开。你可以继续输入新任务。\n")

        print("\n🔄 正在关闭浏览器...")
        await self._executor.close()
        print("👋 已退出。")


def _print_banner() -> None:
    print("\n" + "=" * 60)
    print("✅ 任务执行完成！浏览器保持打开。")
    print("💡 你可以在浏览器中手动操作，也可以在下方输入新任务。")
    print("   输入 quit / exit / q 退出程序并关闭浏览器。")
    print("=" * 60 + "\n")
