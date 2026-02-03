from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    distill_model: str
    agent_model: str
    openai_base_url: str | None
    openai_timeout: float
    openai_max_retries: int
    llm_temperature: float
    llm_max_tokens: int


def load_settings() -> Settings:
    data_dir = Path(os.getenv("EXOGRAM_DATA_DIR", "./data")).resolve()
    distill_model = os.getenv("EXOGRAM_DISTILL_MODEL", "gpt-4o")
    agent_model = os.getenv("EXECUTION_MODEL") or os.getenv("EXOGRAM_AGENT_MODEL", "gpt-4o")
    openai_base_url = os.getenv("OPENAI_BASE_URL") or None
    openai_timeout = float(os.getenv("EXOGRAM_OPENAI_TIMEOUT", "120"))
    openai_max_retries = int(os.getenv("EXOGRAM_OPENAI_MAX_RETRIES", "3"))
    llm_temperature = float(os.getenv("EXOGRAM_LLM_TEMPERATURE", "0.0"))
    llm_max_tokens = int(os.getenv("EXOGRAM_LLM_MAX_TOKENS", "16384"))
    return Settings(
        data_dir=data_dir,
        distill_model=distill_model,
        agent_model=agent_model,
        openai_base_url=openai_base_url,
        openai_timeout=openai_timeout,
        openai_max_retries=openai_max_retries,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )
