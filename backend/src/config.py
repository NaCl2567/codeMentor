# config.py
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TutorConfig:
    """智能编程导师全局配置，默认使用 DeepSeek 模型。"""

    # ---- LLM 设置 ----
    llm_provider: str = "deepseek"           # 可选: deepseek, openai, ollama, lmstudio 等
    llm_model_id: str = "deepseek-chat"      # DeepSeek 默认模型
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None       # 若为空则使用各 provider 默认值

    # 本地模型备选（当 provider 为 ollama / lmstudio 时使用）
    local_llm: Optional[str] = None          # 例如 "llama3:8b"
    ollama_base_url: str = "http://localhost:11434"
    lmstudio_base_url: str = "http://localhost:1234/v1"

    # ---- 笔记与工作区 ----
    enable_notes: bool = True
    notes_workspace: str = "./tutor_notes"   # 存放笔记、报告等 Markdown 文件

    # ---- 其他服务配置 ----
    max_history_turns: int = 10
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> TutorConfig:
        """从环境变量加载配置，未设置时使用默认值。"""
        provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
        model_id = os.getenv("LLM_MODEL_ID", "deepseek-chat").strip()
        api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")

        local_llm = os.getenv("LOCAL_LLM")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        lmstudio_url = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")

        enable_notes = os.getenv("ENABLE_NOTES", "true").strip().lower() in ("true", "1", "yes")
        notes_ws = os.getenv("NOTES_WORKSPACE", "./tutor_notes")

        max_history = int(os.getenv("MAX_HISTORY_TURNS", "10"))
        temp = float(os.getenv("LLM_TEMPERATURE", "0.2"))

        return cls(
            llm_provider=provider,
            llm_model_id=model_id,
            llm_api_key=api_key,
            llm_base_url=base_url,
            local_llm=local_llm,
            ollama_base_url=ollama_url,
            lmstudio_base_url=lmstudio_url,
            enable_notes=enable_notes,
            notes_workspace=notes_ws,
            max_history_turns=max_history,
            temperature=temp,
        )

    def sanitized_ollama_url(self) -> str:
        """确保 Ollama URL 以 http:// 开头，去除尾部斜杠。"""
        url = self.ollama_base_url.strip()
        if not url.startswith("http"):
            url = f"http://{url}"
        return url.rstrip("/")