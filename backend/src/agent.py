from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterator

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from .config import TutorConfig
from .models import Exercise, LearningPath, ReviewReport, TutorState
from .prompts import (
    code_reviewer_prompt,
    exercise_designer_prompt,
    path_planner_prompt,
    tutor_orchestrator_prompt,
)
from .services.exercise_service import ExerciseService
from .services.leetcode_mcp_tools import create_public_leetcode_mcp_tools
from .services.memory_service import MemoryService
from .services.path_service import PathService
from .services.review_service import ReviewService

logger = logging.getLogger(__name__)


class CodeTutorAgent:
    def __init__(self, config: TutorConfig | None = None):
        self.config = config or TutorConfig.from_env()
        self.llm = self._init_llm()

        self.note_tool = NoteTool(workspace=self.config.notes_workspace) if self.config.enable_notes else None
        self.base_tools_registry = self._create_base_tools_registry()
        self.leetcode_mcp_tools = self._create_leetcode_mcp_tools()

        self.orchestrator_agent = self._create_tool_aware_agent(
            name="导师主控",
            system_prompt=tutor_orchestrator_prompt.strip(),
            tool_registry=self.base_tools_registry,
        )
        self.exercise_agent = self._create_tool_aware_agent(
            name="练习设计师",
            system_prompt=exercise_designer_prompt.strip(),
            tool_registry=self._compose_registry(include_leetcode=True),
        )
        self.reviewer_agent = self._create_tool_aware_agent(
            name="代码审查专家",
            system_prompt=code_reviewer_prompt.strip(),
            tool_registry=self._compose_registry(include_leetcode=True),
        )
        self.planner_agent = self._create_tool_aware_agent(
            name="学习路径规划师",
            system_prompt=path_planner_prompt.strip(),
            tool_registry=self.base_tools_registry,
        )

        self.memory_service = MemoryService(self.config, note_tool=self.note_tool)
        self.exercise_service = ExerciseService(self.exercise_agent, self.config, self.memory_service)
        self.review_service = ReviewService(self.reviewer_agent, self.config, self.memory_service)
        self.path_service = PathService(self.planner_agent, self.config, self.memory_service)

        self.active_sessions: Dict[str, TutorState] = {}

    def _init_llm(self) -> HelloAgentsLLM:
        llm_kwargs: dict[str, Any] = {"temperature": float(self.config.temperature)}
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

    def _create_tool_aware_agent(
        self, *, name: str, system_prompt: str, tool_registry: ToolRegistry | None
    ) -> ToolAwareSimpleAgent:
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=tool_registry is not None,
            tool_registry=tool_registry,
        )

    def _create_base_tools_registry(self) -> ToolRegistry | None:
        if not self.note_tool:
            return None
        registry = ToolRegistry()
        registry.register_tool(self.note_tool)
        return registry

    def _create_leetcode_mcp_tools(self) -> list[Any]:
        return create_public_leetcode_mcp_tools(self.config)

    def _compose_registry(self, *, include_leetcode: bool) -> ToolRegistry | None:
        registry = ToolRegistry()
        has_tools = False
        if self.note_tool:
            registry.register_tool(self.note_tool)
            has_tools = True
        if include_leetcode:
            for tool in self.leetcode_mcp_tools:
                registry.register_tool(tool)
                has_tools = True
        return registry if has_tools else None

    def chat(self, user_id: str, message: str) -> str:
        state = self._get_or_create_state(user_id)
        intent, params = self._classify_intent(state, message)
        response = self._run_by_intent(state, message, intent, params)
        state.add_interaction(message, response)
        self.memory_service.record_interaction(
            state,
            user_msg=message,
            assistant_msg=response,
            intent=intent,
            params=params,
        )
        return response

    def chat_with_intent(self, user_id: str, message: str, intent: str, params: dict[str, Any]) -> str:
        state = self._get_or_create_state(user_id)
        response = self._run_by_intent(state, message, intent, params)
        state.add_interaction(message, response)
        self.memory_service.record_interaction(
            state,
            user_msg=message,
            assistant_msg=response,
            intent=intent,
            params=params,
        )
        return response

    def chat_stream(self, user_id: str, message: str) -> Iterator[dict[str, Any]]:
        state = self._get_or_create_state(user_id)
        yield {"type": "status", "message": "正在分析意图..."}
        intent, params = self._classify_intent(state, message)
        original_params = params
        params = {**params, "_user_message": message}
        response = ""

        if intent == "request_exercise":
            yield from self.exercise_service.generate_exercise_stream(state, params)
            response = state.active_exercise.to_markdown() if state.active_exercise else ""
        elif intent == "submit_code":
            yield from self.review_service.review_code_stream(state, params)
            response = state.last_review_report.markdown if state.last_review_report else ""
        elif intent == "learning_path":
            yield from self.path_service.plan_path_stream(state, params)
            response = state.active_learning_path.render() if state.active_learning_path else ""
        else:
            chunks = []
            for chunk in self.orchestrator_agent.stream_run(self._build_context_prompt(state, message)):
                chunks.append(chunk)
                yield {"type": "chat_chunk", "content": chunk}
            response = "".join(chunks)
        state.add_interaction(message, response)
        self.memory_service.record_interaction(
            state,
            user_msg=message,
            assistant_msg=response,
            intent=intent,
            params=original_params,
        )
        yield {"type": "done"}

    def _run_by_intent(self, state: TutorState, message: str, intent: str, params: dict[str, Any]) -> str:
        params = {**params, "_user_message": message}
        if intent == "request_exercise":
            result = self.exercise_service.generate_exercise(state, params)
            return self._format_exercise_response(result)
        if intent == "submit_code":
            result = self.review_service.review_code(state, params)
            return self._format_review_response(result)
        if intent == "learning_path":
            result = self.path_service.plan_path(state, params)
            return self._format_path_response(result)
        response = self.orchestrator_agent.run(self._build_context_prompt(state, message))
        rerouted = self._intent_from_response_json(response, message)
        if rerouted:
            reroute_intent, reroute_params = rerouted
            if reroute_intent != "chat":
                return self._run_by_intent(state, message, reroute_intent, reroute_params)
        return response

    def _get_or_create_state(self, user_id: str) -> TutorState:
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = TutorState(user_id=user_id)
            self.memory_service.hydrate_state(self.active_sessions[user_id])
        return self.active_sessions[user_id]

    def _classify_intent(self, state: TutorState, message: str) -> tuple[str, dict[str, Any]]:
        rule_result = self._classify_intent_by_rules(message)
        if rule_result:
            return rule_result

        prompt = (
            f"当前用户画像：{state.user_profile.summary()}\n"
            f"用户输入：{message}\n"
            "请判断意图类型（request_exercise / submit_code / learning_path / chat）并提取参数。\n"
            '输出 JSON: {"intent": "...", "params": {...}}'
        )
        raw = self.orchestrator_agent.run(prompt)

        try:
            json_text = self._extract_first_json_object(raw)
            if not json_text:
                return "chat", {}
            data = json.loads(json_text)
            intent = data.get("intent", "chat")
            params = data.get("params", {})
            if isinstance(intent, str) and isinstance(params, dict):
                intent = self._normalize_intent(intent.strip().lower(), params, message)
                return intent, params
        except Exception as e:
            logger.warning("intent parse failed, fallback chat: %s", e)

        return "chat", {}

    def _intent_from_response_json(self, response: str, message: str) -> tuple[str, dict[str, Any]] | None:
        json_text = self._extract_first_json_object(response)
        if not json_text:
            return None
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            return None
        intent = data.get("intent")
        params = data.get("params", {})
        if not isinstance(intent, str) or not isinstance(params, dict):
            return None
        intent = self._normalize_intent(intent.strip().lower(), params, message)
        return intent, params

    @staticmethod
    def _extract_first_json_object(text: str) -> str | None:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None

    @staticmethod
    def _normalize_intent(intent: str, params: dict[str, Any], message: str) -> str:
        allowed = {"request_exercise", "submit_code", "learning_path", "chat"}
        if intent not in allowed:
            intent = "chat"

        # Fallback correction: intent is chat, but params/message clearly indicates exercise request.
        if intent == "chat":
            exercise_keys = {"topic", "language", "difficulty", "context"}
            has_exercise_params = any(k in params for k in exercise_keys)
            msg = message.lower()
            has_exercise_signal = any(x in msg for x in ["来一题", "出题", "练习", "题目", "动态规划", "dp"])
            if has_exercise_params and has_exercise_signal:
                return "request_exercise"
        return intent

    @staticmethod
    def _classify_intent_by_rules(message: str) -> tuple[str, dict[str, Any]] | None:
        msg = message.strip()
        lowered = msg.lower()

        if "```" in msg:
            language = CodeTutorAgent._extract_language(msg) or "Python"
            return "submit_code", {"code": msg, "language": language}

        if any(x in lowered for x in ["学习路径", "学习计划", "路线", "roadmap", "下一步学什么"]):
            return "learning_path", {"goal": msg}

        exercise_signals = ["来一题", "来一道", "出题", "练习", "刷题", "题目", "leetcode", "力扣"]
        has_exercise_signal = any(signal in lowered for signal in exercise_signals)
        if not has_exercise_signal:
            return None

        params: dict[str, Any] = {}
        language = CodeTutorAgent._extract_language(msg)
        if language:
            params["language"] = language
        difficulty = CodeTutorAgent._extract_difficulty(msg)
        if difficulty:
            params["difficulty"] = difficulty
        topic = CodeTutorAgent._extract_topic(msg)
        if topic:
            params["topic"] = topic
        return "request_exercise", params

    @staticmethod
    def _extract_language(message: str) -> str:
        lowered = message.lower()
        language_aliases = {
            "Python": ["python", "py"],
            "JavaScript": ["javascript", "js"],
            "TypeScript": ["typescript", "ts"],
            "Java": ["java"],
            "C++": ["c++", "cpp"],
            "Go": ["golang", "go"],
        }
        for language, aliases in language_aliases.items():
            if any(alias in lowered for alias in aliases):
                return language
        return ""

    @staticmethod
    def _extract_difficulty(message: str) -> str:
        lowered = message.lower()
        difficulty_aliases = {
            "基础": ["beginner", "easy", "入门", "简单", "基础"],
            "进阶": ["intermediate", "medium", "中等", "进阶"],
            "挑战": ["advanced", "hard", "困难", "挑战"],
        }
        for difficulty, aliases in difficulty_aliases.items():
            if any(alias in lowered for alias in aliases):
                return difficulty
        return ""

    @staticmethod
    def _extract_topic(message: str) -> str:
        topic_aliases = {
            "回溯算法": ["回溯", "backtracking"],
            "动态规划": ["动态规划", "dp", "dynamic programming"],
            "哈希表": ["哈希", "hash", "hash-table"],
            "数组": ["数组", "列表", "array", "list"],
            "字符串": ["字符串", "string"],
            "双指针": ["双指针", "two pointers", "two-pointers"],
            "滑动窗口": ["滑动窗口", "sliding window", "sliding-window"],
            "二分查找": ["二分", "binary search", "binary-search"],
            "栈": ["栈", "stack"],
            "队列": ["队列", "queue"],
            "树": ["二叉树", "树", "tree"],
            "图": ["图", "graph"],
            "贪心": ["贪心", "greedy"],
        }
        lowered = message.lower()
        found = []
        for topic, aliases in topic_aliases.items():
            if any(alias in lowered for alias in aliases):
                found.append(topic)
        return " ".join(found)

    def _build_context_prompt(self, state: TutorState, message: str) -> str:
        history = state.recent_history(limit=5)
        memory_context = self.memory_service.get_runtime_context(state.user_id, message)
        memory_block = f"\n相关长期记忆：\n{memory_context}\n" if memory_context else ""
        return f"{history}{memory_block}\n用户：{message}\n助手："

    def _format_exercise_response(self, exercise: Exercise) -> str:
        return exercise.to_markdown()

    def _format_review_response(self, report: ReviewReport) -> str:
        return report.markdown

    def _format_path_response(self, path: LearningPath) -> str:
        return path.render()
