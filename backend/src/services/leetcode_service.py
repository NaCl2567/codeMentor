from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from ..config import TutorConfig
from ..models import Exercise, LeetCodeProblem, TutorState
from .leetcode_mcp_client import LeetCodeMCPClient

logger = logging.getLogger(__name__)


DIFFICULTY_MAP = {
    "easy": "EASY",
    "beginner": "EASY",
    "入门": "EASY",
    "简单": "EASY",
    "基础": "EASY",
    "medium": "MEDIUM",
    "intermediate": "MEDIUM",
    "中等": "MEDIUM",
    "进阶": "MEDIUM",
    "hard": "HARD",
    "advanced": "HARD",
    "困难": "HARD",
    "挑战": "HARD",
}

TAG_ALIASES = {
    "array": ["array", "数组", "列表", "list"],
    "string": ["string", "字符串"],
    "hash-table": ["hash-table", "hash", "哈希", "字典", "map", "set"],
    "two-pointers": ["two-pointers", "双指针"],
    "sliding-window": ["sliding-window", "滑动窗口"],
    "binary-search": ["binary-search", "二分", "二分查找"],
    "dynamic-programming": ["dynamic-programming", "动态规划", "dp"],
    "greedy": ["greedy", "贪心"],
    "sorting": ["sorting", "排序"],
    "linked-list": ["linked-list", "链表"],
    "stack": ["stack", "栈"],
    "queue": ["queue", "队列"],
    "heap-priority-queue": ["heap-priority-queue", "heap", "堆", "优先队列"],
    "tree": ["tree", "树"],
    "binary-tree": ["binary-tree", "二叉树"],
    "graph": ["graph", "图"],
    "depth-first-search": ["depth-first-search", "dfs", "深度优先"],
    "breadth-first-search": ["breadth-first-search", "bfs", "广度优先"],
    "backtracking": ["backtracking", "回溯"],
    "matrix": ["matrix", "矩阵"],
    "simulation": ["simulation", "模拟"],
}


class LeetCodeService:
    """Select a suitable online LeetCode problem from public problem metadata."""

    def __init__(self, config: TutorConfig) -> None:
        self.config = config
        self.mcp_client = LeetCodeMCPClient(config)

    def select_exercise(self, state: TutorState, params: dict[str, Any]) -> Exercise | None:
        if not self.config.enable_leetcode:
            return None

        tags = self._infer_tags(state, params)
        difficulty = self._infer_difficulty(state, params)
        keyword = self._infer_keyword(state, params)

        try:
            candidates = self._search_candidates(tags=tags, difficulty=difficulty, keyword=keyword)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning("LeetCode lookup failed, fallback to LLM: %s", exc)
            return None

        if not candidates:
            return None

        selected = self._rank_candidates(candidates, tags, difficulty)[0]
        return self._to_exercise(selected, params, state, tags)

    def _search_candidates(self, *, tags: list[str], difficulty: str, keyword: str) -> list[LeetCodeProblem]:
        queries: list[dict[str, Any]] = []
        if tags:
            queries.append({"difficulty": difficulty, "tags": tags})
        if keyword:
            queries.append({"difficulty": difficulty, "searchKeywords": keyword})
        queries.append({"difficulty": difficulty})

        problems: dict[str, LeetCodeProblem] = {}
        if self.config.enable_leetcode_mcp:
            for filters in queries:
                try:
                    mcp_candidates = self.mcp_client.search_problems(
                        tags=list(filters.get("tags") or []),
                        difficulty=str(filters.get("difficulty") or ""),
                        keyword=str(filters.get("searchKeywords") or ""),
                        limit=self.config.leetcode_query_limit,
                    )
                except Exception as exc:
                    logger.warning("LeetCode MCP search failed, fallback to GraphQL: %s", exc)
                    mcp_candidates = []
                for problem in mcp_candidates:
                    if problem.paid_only:
                        continue
                    detail = self.mcp_client.get_problem(problem.title_slug) if problem.title_slug else None
                    if detail:
                        problem = self._merge_problem(problem, detail)
                    problems[problem.title_slug] = problem
                if problems:
                    return list(problems.values())

        for filters in queries:
            for problem in self._fetch_problemset(filters):
                if problem.paid_only:
                    continue
                problems[problem.title_slug] = problem
            if problems:
                break
        return list(problems.values())

    def _fetch_problemset(self, filters: dict[str, Any]) -> list[LeetCodeProblem]:
        query = """
        query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
          problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
          ) {
            questions: data {
              acRate
              difficulty
              frontendQuestionId: questionFrontendId
              paidOnly: isPaidOnly
              title
              titleSlug
              topicTags {
                name
                slug
              }
            }
          }
        }
        """
        body = json.dumps(
            {
                "query": query,
                "variables": {
                    "categorySlug": "",
                    "skip": 0,
                    "limit": self.config.leetcode_query_limit,
                    "filters": filters,
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.config.leetcode_graphql_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CodeTutorAgent/0.1",
                "Referer": self._problemset_referer(),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.leetcode_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("errors"):
            raise ValueError(payload["errors"])

        questions = payload.get("data", {}).get("problemsetQuestionList", {}).get("questions", [])
        return [self._parse_problem(item) for item in questions]

    def _parse_problem(self, item: dict[str, Any]) -> LeetCodeProblem:
        title_slug = str(item.get("titleSlug", ""))
        tags = item.get("topicTags") or []
        return LeetCodeProblem(
            frontend_question_id=str(item.get("frontendQuestionId", "")),
            title=str(item.get("title", "")),
            title_slug=title_slug,
            difficulty=str(item.get("difficulty", "")),
            ac_rate=float(item.get("acRate") or 0),
            paid_only=bool(item.get("paidOnly")),
            topic_tags=[str(tag.get("slug", "")) for tag in tags if tag.get("slug")],
            topic_names=[str(tag.get("name", "")) for tag in tags if tag.get("name")],
            url=f"{self.config.leetcode_problem_url_base.rstrip('/')}/{title_slug}/",
        )

    def _rank_candidates(
        self, candidates: list[LeetCodeProblem], desired_tags: list[str], desired_difficulty: str
    ) -> list[LeetCodeProblem]:
        def score(problem: LeetCodeProblem) -> float:
            tag_overlap = len(set(desired_tags) & set(problem.topic_tags))
            difficulty_bonus = 2.0 if problem.difficulty.upper() == desired_difficulty else 0.0
            ac_rate_balance = max(0.0, 100.0 - abs(problem.ac_rate - 55.0)) / 100.0
            return tag_overlap * 3.0 + difficulty_bonus + ac_rate_balance

        return sorted(candidates, key=score, reverse=True)

    def _to_exercise(
        self, problem: LeetCodeProblem, params: dict[str, Any], state: TutorState, desired_tags: list[str]
    ) -> Exercise:
        language = str(params.get("language") or state.user_profile.preferred_language)
        difficulty = self._display_difficulty(problem.difficulty)
        topic_display = ", ".join(problem.topic_names or problem.topic_tags)
        reason = self._selection_reason(problem, state, desired_tags)
        reference_brief = self._reference_solution_brief(problem.topic_tags)
        expected_complexity = self._expected_complexity(problem.topic_tags)
        review_focus = self._review_focus(problem.topic_tags)
        description = (
            problem.content
            or "这次练习从 LeetCode 中文站在线题库中选择。请打开题目链接阅读完整中文题面并提交代码；"
            "完成后可以把你的代码贴回这里，我会基于当前题目上下文做 review。"
        )
        example_lines = [f"LeetCode 中文站链接：{problem.url}", f"题目标签：{topic_display}", f"通过率：{problem.ac_rate:.1f}%"]
        if problem.examples:
            example_lines.append("示例摘要：")
            example_lines.extend(problem.examples[:3])
        if problem.constraints:
            example_lines.append("约束摘要：")
            example_lines.extend(problem.constraints[:8])
        return Exercise(
            id=problem.frontend_question_id,
            title=f"{problem.frontend_question_id}. {problem.title}" if problem.frontend_question_id else problem.title,
            language=language,
            difficulty=difficulty,
            tags=problem.topic_tags,
            description=description,
            example="\n".join(example_lines),
            starter_code="",
            test_cases=[],
            source="LeetCode 中文站 MCP" if problem.content else "LeetCode 中文站",
            source_url=problem.url,
            title_slug=problem.title_slug,
            selection_reason=reason,
            reference_solution_brief=reference_brief,
            expected_complexity=expected_complexity,
            review_focus=review_focus,
        )

    @staticmethod
    def _merge_problem(base: LeetCodeProblem, detail: LeetCodeProblem) -> LeetCodeProblem:
        data = base.model_dump()
        detail_data = detail.model_dump()
        for key, value in detail_data.items():
            if value not in ("", [], None, 0, 0.0):
                data[key] = value
        if not data.get("topic_tags"):
            data["topic_tags"] = base.topic_tags
        if not data.get("topic_names"):
            data["topic_names"] = base.topic_names
        return LeetCodeProblem.model_validate(data)

    def _problemset_referer(self) -> str:
        base = self.config.leetcode_problem_url_base.rstrip("/")
        if base.endswith("/problems"):
            return base[: -len("/problems")] + "/problemset/"
        return base + "/problemset/"

    def _selection_reason(self, problem: LeetCodeProblem, state: TutorState, desired_tags: list[str]) -> str:
        overlaps = [tag for tag in desired_tags if tag in problem.topic_tags]
        pieces = []
        if overlaps:
            pieces.append(f"匹配当前训练主题：{', '.join(overlaps)}")
        if state.active_learning_path and state.active_learning_path.stages:
            idx = state.active_learning_path.current_stage_index
            if 0 <= idx < len(state.active_learning_path.stages):
                pieces.append(f"贴合当前学习阶段：{state.active_learning_path.stages[idx].topic}")
        if state.user_profile.weak_skills:
            pieces.append(f"参考薄弱点：{', '.join(state.user_profile.weak_skills)}")
        pieces.append(f"难度为 {self._display_difficulty(problem.difficulty)}，通过率 {problem.ac_rate:.1f}%")
        return "；".join(pieces)

    def _infer_difficulty(self, state: TutorState, params: dict[str, Any]) -> str:
        raw = str(params.get("difficulty") or "").strip().lower()
        if raw in DIFFICULTY_MAP:
            return DIFFICULTY_MAP[raw]
        if state.user_profile.current_level == "advanced":
            return "HARD"
        if state.user_profile.current_level == "intermediate":
            return "MEDIUM"
        return "EASY"

    def _infer_tags(self, state: TutorState, params: dict[str, Any]) -> list[str]:
        texts = [
            str(params.get("topic") or ""),
            str(params.get("context") or ""),
            str(params.get("_user_message") or ""),
            " ".join(state.user_profile.weak_skills),
        ]
        if state.active_learning_path and state.active_learning_path.stages:
            idx = state.active_learning_path.current_stage_index
            if 0 <= idx < len(state.active_learning_path.stages):
                stage = state.active_learning_path.stages[idx]
                texts.extend([stage.topic, stage.objectives])

        combined = " ".join(texts).lower()
        tags: list[str] = []
        for slug, aliases in TAG_ALIASES.items():
            if any(alias.lower() in combined for alias in aliases):
                tags.append(slug)
        return tags[:3]

    def _infer_keyword(self, state: TutorState, params: dict[str, Any]) -> str:
        for key in ("topic", "context", "_user_message"):
            value = str(params.get(key) or "").strip()
            if value:
                return self._clean_keyword(value)
        if state.user_profile.weak_skills:
            return self._clean_keyword(state.user_profile.weak_skills[0])
        return ""

    @staticmethod
    def _clean_keyword(value: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", value)
        return " ".join(words[:6])

    @staticmethod
    def _display_difficulty(difficulty: str) -> str:
        mapping = {"EASY": "基础", "MEDIUM": "进阶", "HARD": "挑战"}
        return mapping.get(difficulty.upper(), difficulty)

    @staticmethod
    def _reference_solution_brief(tags: list[str]) -> str:
        tag_set = set(tags)
        if {"array", "hash-table"} <= tag_set:
            return "优先考虑一次遍历配合哈希表记录已见元素或所需补数，避免双重循环。"
        if "sliding-window" in tag_set:
            return "维护左右边界和窗口内状态，按约束扩张/收缩窗口，确保每个元素进出窗口次数有限。"
        if "two-pointers" in tag_set:
            return "根据有序性或区间条件移动左右指针，用局部判断排除不可能答案。"
        if "binary-search" in tag_set:
            return "确定单调条件，在搜索空间上二分，并仔细处理边界与终止条件。"
        if "dynamic-programming" in tag_set:
            return "定义状态含义、初始状态和转移方程，检查是否能滚动数组优化空间。"
        if "backtracking" in tag_set:
            return "用递归构造候选解，按约束剪枝，并在回溯时恢复现场。"
        if {"tree", "binary-tree"} & tag_set:
            return "根据题意选择 DFS 或 BFS，明确递归返回值或层序遍历队列中的状态。"
        if "graph" in tag_set:
            return "建模节点和边后选择 BFS/DFS/最短路等遍历策略，注意 visited 与连通分量。"
        if "stack" in tag_set:
            return "使用栈保存尚未匹配或待处理的元素，遇到可消解条件时弹出并更新答案。"
        if "heap-priority-queue" in tag_set:
            return "用堆维护当前最优候选，避免每次全量排序。"
        if "greedy" in tag_set:
            return "寻找可证明安全的局部最优选择，并关注排序或优先队列是否是贪心前置条件。"
        return "结合题目标签选择合适数据结构，先保证边界条件正确，再优化时间和空间复杂度。"

    @staticmethod
    def _expected_complexity(tags: list[str]) -> str:
        tag_set = set(tags)
        if {"array", "hash-table"} <= tag_set:
            return "通常可做到 O(n) 时间、O(n) 空间。"
        if "sliding-window" in tag_set or "two-pointers" in tag_set:
            return "通常可做到 O(n) 时间、O(1) 或 O(k) 空间。"
        if "binary-search" in tag_set:
            return "通常为 O(log n) 或 O(n log range)，空间接近 O(1)。"
        if "dynamic-programming" in tag_set:
            return "取决于状态规模，常见为 O(状态数 * 转移成本)。"
        if {"tree", "binary-tree", "graph"} & tag_set:
            return "通常为 O(V+E) 或 O(n) 时间，空间取决于递归栈/队列/visited。"
        if "heap-priority-queue" in tag_set:
            return "通常为 O(n log k) 或 O(n log n)，取决于堆大小。"
        return "应优于明显暴力解，并解释主要时间、空间来源。"

    @staticmethod
    def _review_focus(tags: list[str]) -> list[str]:
        focus = ["是否正确处理空输入、最小规模、重复值等边界情况。"]
        tag_set = set(tags)
        if "hash-table" in tag_set:
            focus.append("哈希表 key/value 设计是否能覆盖重复元素和下标冲突。")
        if "two-pointers" in tag_set or "sliding-window" in tag_set:
            focus.append("指针移动条件是否保证不会漏解、死循环或越界。")
        if "binary-search" in tag_set:
            focus.append("二分边界、mid 更新和返回值是否符合单调条件。")
        if "dynamic-programming" in tag_set:
            focus.append("状态定义、初值、转移顺序和空间优化是否一致。")
        if {"tree", "binary-tree", "graph"} & tag_set:
            focus.append("遍历是否正确维护 visited/递归返回值，并避免重复访问。")
        if "stack" in tag_set:
            focus.append("入栈/出栈条件是否匹配题目约束。")
        focus.append("复杂度是否接近期望解法，是否存在可避免的 O(n^2) 暴力结构。")
        return focus
