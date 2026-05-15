# config.py
from __future__ import annotations
import os
import shlex
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
    enable_memory: bool = True
    memory_store_path: str = "./backend/data/user_memory.json"

    # ---- LeetCode 题库配置 ----
    enable_leetcode: bool = True
    leetcode_site: str = "cn"
    leetcode_graphql_url: str = "https://leetcode.cn/graphql"
    leetcode_problem_url_base: str = "https://leetcode.cn/problems"
    leetcode_query_limit: int = 50
    leetcode_timeout_seconds: float = 8.0

    # ---- LeetCode MCP 配置（stdio，无登录工具默认不调用）----
    enable_leetcode_mcp: bool = False
    leetcode_mcp_command: str = "npx"
    leetcode_mcp_args: list[str] = field(default_factory=lambda: ["-y", "@jinzcdev/leetcode-mcp-server", "--site", "cn"])
    leetcode_mcp_cwd: Optional[str] = None
    leetcode_mcp_tool_timeout_seconds: float = 15.0
    expose_leetcode_mcp_tools_to_agents: bool = True

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
        enable_memory = os.getenv("ENABLE_MEMORY", "true").strip().lower() in ("true", "1", "yes")
        memory_store_path = os.getenv("MEMORY_STORE_PATH", "./backend/data/user_memory.json")
        enable_leetcode = os.getenv("ENABLE_LEETCODE", "true").strip().lower() in ("true", "1", "yes")
        leetcode_site = os.getenv("LEETCODE_SITE", "cn").strip().lower() or "cn"
        leetcode_url = os.getenv("LEETCODE_GRAPHQL_URL", "https://leetcode.cn/graphql")
        leetcode_problem_base = os.getenv("LEETCODE_PROBLEM_URL_BASE", "https://leetcode.cn/problems")
        leetcode_limit = int(os.getenv("LEETCODE_QUERY_LIMIT", "50"))
        leetcode_timeout = float(os.getenv("LEETCODE_TIMEOUT_SECONDS", "8"))
        enable_leetcode_mcp = os.getenv("ENABLE_LEETCODE_MCP", "false").strip().lower() in ("true", "1", "yes")
        leetcode_mcp_command = os.getenv("LEETCODE_MCP_COMMAND", "npx")
        leetcode_mcp_args = cls._parse_args_env(
            os.getenv("LEETCODE_MCP_ARGS"),
            ["-y", "@jinzcdev/leetcode-mcp-server", "--site", "cn"],
        )
        leetcode_mcp_cwd = os.getenv("LEETCODE_MCP_CWD") or None
        leetcode_mcp_timeout = float(os.getenv("LEETCODE_MCP_TOOL_TIMEOUT_SECONDS", "15"))
        expose_mcp_tools = os.getenv("EXPOSE_LEETCODE_MCP_TOOLS", "true").strip().lower() in ("true", "1", "yes")

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
            enable_memory=enable_memory,
            memory_store_path=memory_store_path,
            enable_leetcode=enable_leetcode,
            leetcode_site=leetcode_site,
            leetcode_graphql_url=leetcode_url,
            leetcode_problem_url_base=leetcode_problem_base,
            leetcode_query_limit=leetcode_limit,
            leetcode_timeout_seconds=leetcode_timeout,
            enable_leetcode_mcp=enable_leetcode_mcp,
            leetcode_mcp_command=leetcode_mcp_command,
            leetcode_mcp_args=leetcode_mcp_args,
            leetcode_mcp_cwd=leetcode_mcp_cwd,
            leetcode_mcp_tool_timeout_seconds=leetcode_mcp_timeout,
            expose_leetcode_mcp_tools_to_agents=expose_mcp_tools,
        )

    def sanitized_ollama_url(self) -> str:
        """确保 Ollama URL 以 http:// 开头，去除尾部斜杠。"""
        url = self.ollama_base_url.strip()
        if not url.startswith("http"):
            url = f"http://{url}"
        return url.rstrip("/")

    @staticmethod
    def _parse_args_env(raw: str | None, default: list[str]) -> list[str]:
        if not raw:
            return default
        raw = raw.strip()
        if not raw:
            return default
        try:
            if raw.startswith("["):
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
        except Exception:
            pass
        return shlex.split(raw)
