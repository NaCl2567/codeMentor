
from __future__ import annotations
import logging
import re
from typing import Any, Iterator

from hello_agents import ToolAwareSimpleAgent
from ..config import TutorConfig
from ..models import TutorState, ReviewReport
from ..prompt_utils import safe_format_prompt
from ..prompts import code_reviewer_prompt

logger = logging.getLogger(__name__)


class ReviewService:
    """封装代码审查 Agent 的调用与结果解析。

    Agent 自行决定是否调用 LeetCode MCP 工具获取题目详情或题解，
    service 层只负责组装 prompt、调用 agent、解析输出。
    """

    def __init__(self, reviewer_agent: ToolAwareSimpleAgent, config: TutorConfig) -> None:
        self.agent = reviewer_agent
        self.config = config

    def review_code(self, state: TutorState, params: dict) -> ReviewReport:
        """同步审查代码，返回结构化的 ReviewReport。
        params 必须包含 "code"，可选 "language" 和 "problem_description"。
        """
        code = params.get("code", "")
        language = params.get("language", state.user_profile.preferred_language)
        problem = params.get("problem_description", "")

        prompt = self._build_prompt(state, code, language, problem)
        raw_response = self.agent.run(prompt)

        report = self._parse_response(raw_response, code, language)
        state.last_review_report = report
        return report

    def review_code_stream(self, state: TutorState, params: dict) -> Iterator[dict[str, Any]]:
        """流式审查代码，逐步产出审查内容。
        最终产出 {"type": "review_report", "report": ReviewReport}。
        """
        code = params.get("code", "")
        language = params.get("language", state.user_profile.preferred_language)
        problem = params.get("problem_description", "")

        prompt = self._build_prompt(state, code, language, problem)

        collected_chunks: list[str] = []
        for chunk in self.agent.stream_run(prompt):
            if chunk:
                collected_chunks.append(chunk)
                yield {"type": "review_chunk", "content": chunk}

        full_response = "".join(collected_chunks)
        report = self._parse_response(full_response, code, language)
        state.last_review_report = report
        yield {"type": "review_report", "report": report}

    def _build_prompt(self, state: TutorState, code: str, language: str, problem: str) -> str:
        """构造发给审查 Agent 的完整 prompt，注入题目线索供 agent 自主调用工具。"""
        user_profile_text = state.user_profile.summary()
        history_text = state.recent_history(limit=3)

        active_exercise = state.active_exercise.to_markdown() if state.active_exercise else "无"

        # 提供 titleSlug / source_url 线索，让 agent 自行决定是否调用 MCP 工具
        review_reference = self._build_review_hint(state)

        prompt = safe_format_prompt(
            code_reviewer_prompt,
            user_profile=user_profile_text,
            language=language,
            code=code,
            problem_description=problem or "无",
            active_exercise=active_exercise,
            review_reference=review_reference,
            history=history_text,
        )
        return prompt

    def _build_review_hint(self, state: TutorState) -> str:
        """构建给 agent 的题目线索，引导其使用工具而非注入完整 MCP 数据。"""
        exercise = state.active_exercise
        if not exercise:
            return "无 LeetCode 题目上下文，审查时直接基于代码本身判断。"
        title_slug = getattr(exercise, "title_slug", "") or self._extract_title_slug(
            getattr(exercise, "source_url", "")
        )
        parts: list[str] = []
        if title_slug:
            parts.append(f"titleSlug: {title_slug}")
            parts.append("请使用 `leetcode_mcp_get_problem` 工具获取题目完整约束和示例。")
        if hasattr(exercise, "source_url") and exercise.source_url:
            parts.append(f"source_url: {exercise.source_url}")
        if hasattr(exercise, "tags") and exercise.tags:
            parts.append(f"tags: {', '.join(exercise.tags)}")
            parts.append("如需了解常见解法，可用 `leetcode_mcp_list_problem_solutions` 获取题解参考。")
        if not parts:
            return "无 LeetCode 题目上下文，审查时直接基于代码本身判断。"
        return "\n".join(parts)

    @staticmethod
    def _extract_title_slug(url: str) -> str:
        match = re.search(r"leetcode\.com/problems/([^/]+)/?", url or "")
        return match.group(1) if match else ""

    def _parse_response(self, raw_response: str, original_code: str, language: str) -> ReviewReport:
        """从 Agent 的 Markdown 输出中提取结构化字段。"""
        report = ReviewReport(
            code=original_code,
            language=language,
            overall_score=0,
            lines=len(original_code.splitlines()) if original_code else 0,
        )

        score_match = re.search(r"整体评分[：:]\s*([\d.]+)", raw_response)
        if score_match:
            try:
                report.overall_score = float(score_match.group(1))
            except ValueError:
                pass

        sections = self._extract_sections(raw_response)

        report.critical_issues = sections.get("严重问题", [])
        report.suggestions = sections.get("改进建议", [])
        report.performance_issues = sections.get("性能优化", [])
        report.security_issues = sections.get("安全风险", [])
        report.highlights = sections.get("优秀实践", [])

        code_block_match = re.search(r"```(?:\w+)?\s*\n(.*?)```", raw_response, re.DOTALL)
        if code_block_match:
            report.improved_code = code_block_match.group(1).strip()

        kp_section = sections.get("关联知识点", [])
        report.related_knowledge = [kp.strip() for kp in kp_section if kp.strip()]

        return report

    @staticmethod
    def _extract_sections(markdown_text: str) -> dict[str, list[str]]:
        """根据 Markdown 标题提取各段落下的列表项。"""
        sections: dict[str, list[str]] = {}
        current_section: str | None = None
        for line in markdown_text.splitlines():
            header_match = re.match(r"###\s+(.+?)(?:\s*\(.*\))?$", line)
            if header_match:
                current_section = header_match.group(1).strip()
                if current_section and current_section not in sections:
                    sections[current_section] = []
                continue
            if current_section and line.strip().startswith("- "):
                item = line.strip()[2:].strip()
                if item:
                    sections[current_section].append(item)
        return sections
