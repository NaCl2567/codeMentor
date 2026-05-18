from __future__ import annotations
import logging
import re
from typing import Any, Iterator

from hello_agents import ToolAwareSimpleAgent

from ..config import TutorConfig
from ..models import Exercise, TutorState
from ..prompt_utils import safe_format_prompt
from ..prompts import exercise_designer_prompt
logger = logging.getLogger(__name__)


class ExerciseService:
    """封装练习生成逻辑，将 Agent 的 Markdown 输出解析为 Exercise 对象。

    Agent 自行决定是否调用 LeetCode MCP 工具检索题目，service 层只负责
    组装 prompt、调用 agent、解析输出。
    """

    def __init__(self, agent: ToolAwareSimpleAgent, config: TutorConfig) -> None:
        self.agent = agent
        self.config = config

    def generate_exercise(self, state: TutorState, params: dict[str, Any]) -> Exercise:
        """同步生成一道练习题。Agent 自主决定是否使用 LeetCode MCP 工具。"""
        full_prompt = self._build_full_prompt(state, params)
        raw_output = self.agent.run(full_prompt)
        exercise = self._parse_exercise(raw_output)
        state.active_exercise = exercise
        return exercise

    def generate_exercise_stream(
        self, state: TutorState, params: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        """流式生成练习题，逐步产出 Markdown 块。Agent 自主决定是否使用工具。"""
        full_prompt = self._build_full_prompt(state, params)
        full_text = []
        yield {"type": "exercise_stream_start", "params": params}

        try:
            for chunk in self.agent.stream_run(full_prompt):
                if chunk:
                    full_text.append(chunk)
                    yield {"type": "exercise_chunk", "content": chunk}
        finally:
            full_output = "".join(full_text)
            try:
                exercise = self._parse_exercise(full_output)
                state.active_exercise = exercise
                yield {"type": "exercise_complete", "exercise": exercise.to_dict()}
            except Exception as e:
                logger.error("Failed to parse exercise output: %s", e)
                yield {"type": "exercise_parse_error", "error": str(e), "raw": full_output}

    def _build_full_prompt(self, state: TutorState, params: dict[str, Any]) -> str:
        """组装 prompt，注入用户画像、学习阶段等上下文供 agent 决策。"""
        language = params.get("language", state.user_profile.preferred_language)
        difficulty = params.get("difficulty", "基础")
        topic = params.get("topic", "根据用户薄弱点自动选择")
        user_message = params.get("_user_message", "")
        user_skill_profile = state.user_profile.summary()

        # 附加上下文帮助 agent 判断是否需要调用 LeetCode 工具
        extra_context_parts: list[str] = []
        if state.active_learning_path and state.active_learning_path.stages:
            idx = state.active_learning_path.current_stage_index
            if 0 <= idx < len(state.active_learning_path.stages):
                stage = state.active_learning_path.stages[idx]
                extra_context_parts.append(f"当前学习阶段：{stage.topic}，目标：{stage.objectives}")
        if state.user_profile.weak_skills:
            extra_context_parts.append(f"用户薄弱点：{', '.join(state.user_profile.weak_skills)}")
        extra_context = "\n".join(extra_context_parts)

        prompt = safe_format_prompt(
            exercise_designer_prompt,
            title="{title}",
            language=language,
            difficulty=difficulty,
            tags=topic,
            description="{description}",
            input_format="{input_format}",
            output_format="{output_format}",
            example="{example}",
            starter_code="{starter_code}",
            test_cases="{test_cases}",
            user_skill_profile=user_skill_profile,
        )

        parts = [prompt]
        if extra_context:
            parts.append(f"\n# 额外上下文\n{extra_context}")
        if user_message:
            parts.append(f"\n# 用户原始消息\n{user_message}")
        parts.append("\n请根据上述信息生成一道练习题。如需搜索 LeetCode 请先调用工具。")
        return "\n".join(parts)

    def _parse_exercise(self, raw: str) -> Exercise:
        """从 Agent 返回的 Markdown 文本中提取 Exercise 字段。
        先丢弃 ### 思考过程 块，再解析题目正文。
        """
        # 丢弃思考过程：截取 ## 练习题目：之前的所有内容
        marker = raw.find("## 练习题目：")
        if marker != -1:
            raw = raw[marker:]

        title_match = re.search(r"##\s*练习题目：(.+)", raw)
        title = title_match.group(1).strip() if title_match else "未命名练习"

        lang_match = re.search(r"\*\*语言\*\*：(.+)", raw)
        language = lang_match.group(1).strip() if lang_match else "python"

        diff_match = re.search(r"\*\*难度\*\*：(.+)", raw)
        difficulty = diff_match.group(1).strip() if diff_match else "基础"

        tags_match = re.search(r"\*\*知识点\*\*：(.+)", raw)
        tags = [t.strip() for t in tags_match.group(1).split(",")] if tags_match else []

        source_match = re.search(r"\*\*来源\*\*：(.+)", raw)
        source = source_match.group(1).strip() if source_match else "llm"

        desc_match = re.search(r"###\s*问题描述\s*\n(.*?)\n###", raw, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""

        in_match = re.search(r"###\s*输入格式\s*\n(.*?)\n###", raw, re.DOTALL)
        input_format = in_match.group(1).strip() if in_match else ""

        out_match = re.search(r"###\s*输出格式\s*\n(.*?)\n###", raw, re.DOTALL)
        output_format = out_match.group(1).strip() if out_match else ""

        example_match = re.search(r"###\s*示例\s*\n(.*?)(?=###|\Z)", raw, re.DOTALL)
        example = example_match.group(1).strip() if example_match else ""

        code_match = re.search(r"```(?:python|javascript|c\+\+|java)?\s*\n(.*?)\n```", raw, re.DOTALL)
        starter_code = code_match.group(1) if code_match else ""

        return Exercise(
            title=title,
            language=language,
            difficulty=difficulty,
            tags=tags,
            description=description,
            input_format=input_format,
            output_format=output_format,
            example=example,
            starter_code=starter_code,
            test_cases=[],
            source=source,
        )
