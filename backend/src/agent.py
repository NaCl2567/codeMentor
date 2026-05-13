from __future__ import annotations
import logging
from typing import Any, Dict, Optional, Iterator
from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool  # 可选知识库持久化



from .config import TutorConfig  # 你自己的配置类

from .prompts import (
    tutor_orchestrator_prompt,      # 主控 Agent 系统提示
    exercise_designer_prompt,       # 练习设计师提示
    code_reviewer_prompt,           # 代码审查提示
    path_planner_prompt,            # 学习路径规划提示
)
from .models import TutorState, UserProfile, Exercise, ReviewReport, LearningPath
from .services.exercise_service import ExerciseService
from .services.review_service import ReviewService
from .services.path_service import PathService

logger = logging.getLogger(__name__)


class CodeTutorAgent:
    """智能编程导师主协调 Agent，基于多 Agent 混合架构（ReAct + Plan-and-Solve）。"""

    def __init__(self, config: TutorConfig | None = None):
        self.config = config or TutorConfig.from_env()
        self.llm = self._init_llm()

        # 可选笔记工具，用于持久化用户学习笔记与报告
        self.note_tool = (
            NoteTool(workspace=self.config.notes_workspace)
            if self.config.enable_notes else None
        )
        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry

        # ---------- 创建子 Agent ----------
        # 1. 主控对话 Agent：意图识别、任务分发、状态维护
        self.orchestrator_agent = self._create_tool_aware_agent(
            name="导师主控",
            system_prompt=tutor_orchestrator_prompt.strip(),
        )
        # 2. 练习设计师 Agent（ReAct + 题库/沙箱工具）
        self.exercise_agent = self._create_tool_aware_agent(
            name="练习设计师",
            system_prompt=exercise_designer_prompt.strip(),
        )
        # 3. 代码审查 Agent（ReAct + AST/安全扫描等工具）
        self.reviewer_agent = self._create_tool_aware_agent(
            name="代码审查专家",
            system_prompt=code_reviewer_prompt.strip(),
        )
        # 4. 学习路径规划 Agent（Plan-and-Solve 模式通过系统提示强制“先计划后执行”）
        self.planner_agent = self._create_tool_aware_agent(
            name="学习路径规划师",
            system_prompt=path_planner_prompt.strip(),
        )

        # 服务层封装，用于调用子 Agent 并处理结构化输出
        self.exercise_service = ExerciseService(self.exercise_agent, self.config)
        self.review_service = ReviewService(self.reviewer_agent, self.config)
        self.path_service = PathService(self.planner_agent, self.config)

        # 对话状态（简单版，可用数据库或 Redis 替代）
        self.active_sessions: Dict[str, TutorState] = {}

    # ------------------------------------------------------------------
    # 初始化工具方法（与你的 DeepResearchAgent 类似）
    # ------------------------------------------------------------------
    def _init_llm(self) -> HelloAgentsLLM:
        """根据配置初始化大模型实例。"""
        llm_kwargs: dict[str, Any] = {"temperature": 0.2}
        model_id = self.config.llm_model_id or self.config.local_llm
        if model_id:
            llm_kwargs["model"] = model_id
        provider = (self.config.llm_provider or "").strip()
        if provider:
            llm_kwargs["provider"] = provider
        if provider == "ollama":
            llm_kwargs["base_url"] = self.config.sanitized_ollama_url()
            llm_kwargs["api_key"] = self.config.llm_api_key or "ollama"
        elif provider == "lmstudio":
            llm_kwargs["base_url"] = self.config.lmstudio_base_url
            llm_kwargs["api_key"] = self.config.llm_api_key
        else:
            if self.config.llm_base_url:
                llm_kwargs["base_url"] = self.config.llm_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
        return HelloAgentsLLM(**llm_kwargs)

    def _create_tool_aware_agent(self, *, name: str, system_prompt: str) -> ToolAwareSimpleAgent:
        """创建可调用工具的 Agent 实例。"""
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=self.tools_registry is not None,
            tool_registry=self.tools_registry,
            # 可扩展：tool_call_listener 用于记录工具调用
        )

    # ------------------------------------------------------------------
    # 公开 API：同步/流式对话
    # ------------------------------------------------------------------
    def chat(self, user_id: str, message: str) -> str:
        """处理一次用户输入，返回助手的完整回复。"""
        state = self._get_or_create_state(user_id)
        # 主控 Agent 进行意图分类与分发（ReAct 模式）
        intent, params = self._classify_intent(state, message)

        if intent == "request_exercise":
            result = self.exercise_service.generate_exercise(state, params)
            response = self._format_exercise_response(result)
        elif intent == "submit_code":
            result = self.review_service.review_code(state, params)
            response = self._format_review_response(result)
        elif intent == "learning_path":
            result = self.path_service.plan_path(state, params)
            response = self._format_path_response(result)
        else:
            # 纯对话或无法识别时，由主控 Agent 直接回复
            response = self.orchestrator_agent.run(
                self._build_context_prompt(state, message)
            )
        state.add_interaction(message, response)
        return response

    def chat_stream(self, user_id: str, message: str) -> Iterator[dict[str, Any]]:
        """流式版本，逐步产出事件。"""
        state = self._get_or_create_state(user_id)
        yield {"type": "status", "message": "正在分析意图..."}
        intent, params = self._classify_intent(state, message)

        if intent == "request_exercise":
            yield from self.exercise_service.generate_exercise_stream(state, params)
        elif intent == "submit_code":
            yield from self.review_service.review_code_stream(state, params)
        elif intent == "learning_path":
            yield from self.path_service.plan_path_stream(state, params)
        else:
            for chunk in self.orchestrator_agent.stream_run(
                self._build_context_prompt(state, message)
            ):
                yield {"type": "chat_chunk", "content": chunk}
        yield {"type": "done"}

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------
    def _get_or_create_state(self, user_id: str) -> TutorState:
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = TutorState(user_id=user_id)
        return self.active_sessions[user_id]

    def _classify_intent(self, state: TutorState, message: str) -> tuple[str, dict]:
        """
        使用主控 Agent 识别用户意图，返回意图标签与参数。
        实现方式：向 orchestrator_agent 发送一个专门的分类 prompt，要求输出 JSON。
        """
        prompt = f"""
当前用户画像：{state.user_profile.summary()}
用户输入：{message}
请判断意图类型（request_exercise / submit_code / learning_path / chat）并提取参数。
输出 JSON: {{"intent": "...", "params": {{...}}}}
"""
        raw = self.orchestrator_agent.run(prompt)
        # 简化解析，实际可用 json.loads
        import json, re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("intent", "chat"), data.get("params", {})
        return "chat", {}

    def _build_context_prompt(self, state: TutorState, message: str) -> str:
        """构建包含历史对话的提示。"""
        history = state.recent_history(limit=5)
        return f"{history}\n用户：{message}\n助手："

    # 格式化响应的占位方法
    def _format_exercise_response(self, exercise: Exercise) -> str:
        return f"## 练习题目\n{exercise.description}\n\n```{exercise.language}\n{exercise.starter_code}\n```"

    def _format_review_response(self, report: ReviewReport) -> str:
        return report.markdown

    def _format_path_response(self, path: LearningPath) -> str:
        return path.render()