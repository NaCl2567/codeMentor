from __future__ import annotations
import logging
import re
from typing import Any, Dict, Iterator

from hello_agents import ToolAwareSimpleAgent

from ..config import TutorConfig
from ..models import Exercise, TutorState
from ..prompts import exercise_designer_prompt

logger = logging.getLogger(__name__)


class ExerciseService:
    """封装练习生成逻辑，将 Agent 的 Markdown 输出解析为 Exercise 对象。"""

    def __init__(self, agent: ToolAwareSimpleAgent, config: TutorConfig) -> None:
        self.agent = agent
        self.config = config

    def generate_exercise(self, state: TutorState, params: dict[str, Any]) -> Exercise:
        """同步生成一道练习题。"""
        full_prompt = self._build_full_prompt(state, params)
        raw_output = self.agent.run(full_prompt)
        return self._parse_exercise(raw_output)

    def generate_exercise_stream(
        self, state: TutorState, params: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        """流式生成练习题，逐步产出 Markdown 块。"""
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
                yield {"type": "exercise_complete", "exercise": exercise.to_dict()}
            except Exception as e:
                logger.error("Failed to parse exercise output: %s", e)
                yield {"type": "exercise_parse_error", "error": str(e), "raw": full_output}

    def _build_full_prompt(self, state: TutorState, params: dict[str, Any]) -> str:
        """仅用 exercise_designer_prompt 并填充占位符，不再拼接额外内容。"""
        language = params.get("language", state.user_profile.preferred_language)
        difficulty = params.get("difficulty", "基础")
        topic = params.get("topic", "根据用户薄弱点自动选择")
        user_skill_profile = state.user_profile.summary()

        return exercise_designer_prompt.format(
            title="{title}",               # 由 Agent 生成时自行填写
            language=language,
            difficulty=difficulty,
            tags=topic,                    # 直接使用 topic 作为知识点标签
            description="{description}",
            input_format="{input_format}",
            output_format="{output_format}",
            example="{example}",
            starter_code="{starter_code}",
            test_cases="{test_cases}",
            user_skill_profile=user_skill_profile,
        )

    def _parse_exercise(self, raw: str) -> Exercise:
        """从 Agent 返回的 Markdown 文本中提取 Exercise 字段（逻辑不变）。"""
        title_match = re.search(r"##\s*练习题目：(.+)", raw)
        title = title_match.group(1).strip() if title_match else "未命名练习"

        lang_match = re.search(r"\*\*语言\*\*：(.+)", raw)
        language = lang_match.group(1).strip() if lang_match else "python"

        diff_match = re.search(r"\*\*难度\*\*：(.+)", raw)
        difficulty = diff_match.group(1).strip() if diff_match else "基础"

        tags_match = re.search(r"\*\*知识点\*\*：(.+)", raw)
        tags = [t.strip() for t in tags_match.group(1).split(",")] if tags_match else []

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
        )