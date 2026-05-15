
from __future__ import annotations
import logging
import re
from typing import Any, Iterator

from hello_agents import ToolAwareSimpleAgent
from ..config import TutorConfig
from ..models import TutorState, ReviewReport
from ..prompt_utils import safe_format_prompt
from ..prompts import code_reviewer_prompt
from .leetcode_mcp_client import LeetCodeMCPClient
logger = logging.getLogger(__name__)

class ReviewService:
    """封装代码审查 Agent 的调用与结果解析。"""

    def __init__(self, reviewer_agent: ToolAwareSimpleAgent, config: TutorConfig) -> None:
        self.agent = reviewer_agent
        self.config = config
        self.leetcode_mcp_client = LeetCodeMCPClient(config)

    def review_code(self, state: TutorState, params: dict) -> ReviewReport:
        """
        同步审查代码，返回结构化的 ReviewReport。
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
        """
        流式审查代码，逐步产出审查内容。
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
        """构造发给审查 Agent 的完整 prompt。"""
        user_profile_text = state.user_profile.summary()
        history_text = state.recent_history(limit=3)

        active_exercise = state.active_exercise.to_markdown() if state.active_exercise else "无"
        review_reference = state.active_exercise.review_context() if state.active_exercise else "无"
        if state.active_exercise:
            mcp_reference = self._build_mcp_review_reference(state.active_exercise)
            if mcp_reference:
                review_reference = f"{review_reference}\n\n{mcp_reference}"

        prompt = safe_format_prompt(
            code_reviewer_prompt,
            user_profile=user_profile_text,
            language=language,
            code=code,
            problem_description=problem or "无",
            active_exercise=active_exercise,
            review_reference=review_reference,
            history=history_text,
            timestamp="{timestamp}",   # 保留占位，让 agent 填充
            score="{score}",
            lines="{lines}",
        )
        # 替换残留的格式占位为合理默认值，避免 agent 混淆
        prompt = prompt.replace("{timestamp}", "将由 agent 生成")
        return prompt

    def _build_mcp_review_reference(self, exercise) -> str:
        if not self.config.enable_leetcode_mcp:
            return ""
        title_slug = getattr(exercise, "title_slug", "") or self._extract_title_slug(getattr(exercise, "source_url", ""))
        if not title_slug:
            return ""
        try:
            return self.leetcode_mcp_client.build_review_reference(title_slug)
        except Exception as exc:
            logger.warning("LeetCode MCP review reference failed: %s", exc)
            return ""

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

        # 解析评分
        score_match = re.search(r"整体评分[：:]\s*([\d.]+)", raw_response)
        if score_match:
            try:
                report.overall_score = float(score_match.group(1))
            except ValueError:
                pass

        # 解析各个 section
        sections = self._extract_sections(raw_response)

        report.critical_issues = sections.get("严重问题", [])
        report.suggestions = sections.get("改进建议", [])
        report.performance_issues = sections.get("性能优化", [])
        report.security_issues = sections.get("安全风险", [])
        report.highlights = sections.get("优秀实践", [])

        # 提取改进后代码块
        code_block_match = re.search(r"```(?:\w+)?\s*\n(.*?)```", raw_response, re.DOTALL)
        if code_block_match:
            report.improved_code = code_block_match.group(1).strip()

        # 提取关联知识点（简单列表）
        kp_section = sections.get("关联知识点", [])
        report.related_knowledge = [kp.strip() for kp in kp_section if kp.strip()]

        return report

    @staticmethod
    def _extract_sections(markdown_text: str) -> dict[str, list[str]]:
        """根据 Markdown 标题提取各段落下的列表项。"""
        sections: dict[str, list[str]] = {}
        current_section: str | None = None
        for line in markdown_text.splitlines():
            # 匹配 ### 标题
            header_match = re.match(r"###\s+(.+?)(?:\s*\(.*\))?$", line)
            if header_match:
                current_section = header_match.group(1).strip()
                if current_section and current_section not in sections:
                    sections[current_section] = []
                continue
            # 列表项
            if current_section and line.strip().startswith("- "):
                item = line.strip()[2:].strip()
                if item:
                    sections[current_section].append(item)
        return sections
