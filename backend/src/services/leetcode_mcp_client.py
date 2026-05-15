from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import re
from typing import Any

from ..config import TutorConfig
from ..models import LeetCodeProblem

logger = logging.getLogger(__name__)


PUBLIC_LEETCODE_MCP_TOOLS = {
    "get_daily_challenge",
    "get_problem",
    "search_problems",
    "get_user_profile",
    "get_user_contest_ranking",
    "get_recent_ac_submissions",
    "get_recent_submissions",
    "list_problem_solutions",
    "get_problem_solution",
}


class LeetCodeMCPClient:
    """Synchronous adapter around the stdio LeetCode MCP server."""

    def __init__(self, config: TutorConfig) -> None:
        self.config = config
        self._problem_cache: dict[str, LeetCodeProblem] = {}
        self._solution_cache: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return self.config.enable_leetcode_mcp

    def server_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "transport": "stdio",
            "command": self.config.leetcode_mcp_command,
            "args": self._args_with_site(self.config.leetcode_mcp_args),
        }
        if self.config.leetcode_mcp_cwd:
            config["cwd"] = self.config.leetcode_mcp_cwd
        return config

    def list_public_tools(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            tools = self._run(self._list_tools_async())
            return [tool for tool in tools if tool.get("name") in PUBLIC_LEETCODE_MCP_TOOLS]
        except Exception as exc:
            logger.warning("LeetCode MCP list tools failed: %s", exc)
            return []

    def search_problems(
        self, *, tags: list[str], difficulty: str, keyword: str, limit: int
    ) -> list[LeetCodeProblem]:
        if not self.enabled:
            return []
        arguments: dict[str, Any] = {"limit": limit}
        if tags:
            arguments["tags"] = tags
        if difficulty:
            arguments["difficulty"] = difficulty
        if keyword:
            arguments["searchKeywords"] = keyword

        raw = self.call_tool("search_problems", arguments)
        items = self._extract_problem_items(raw)
        return [self._problem_from_search_item(item) for item in items]

    def get_problem(self, title_slug: str) -> LeetCodeProblem | None:
        if not self.enabled or not title_slug:
            return None
        if title_slug in self._problem_cache:
            return self._problem_cache[title_slug]
        raw = self.call_tool("get_problem", {"titleSlug": title_slug})
        problem = self._problem_from_detail(raw, title_slug)
        if problem:
            self._problem_cache[title_slug] = problem
        return problem

    def build_review_reference(self, title_slug: str) -> str:
        if not self.enabled or not title_slug:
            return ""
        pieces: list[str] = []
        problem = self.get_problem(title_slug)
        if problem:
            pieces.append(f"MCP 题目详情：{problem.title} ({problem.title_slug})")
            if problem.constraints:
                pieces.append("约束：\n" + "\n".join(f"- {item}" for item in problem.constraints[:8]))
            if problem.examples:
                pieces.append("示例摘要：\n" + "\n".join(f"- {item}" for item in problem.examples[:3]))

        solution_summary = self.get_solution_brief(title_slug)
        if solution_summary:
            pieces.append("MCP 题解摘要（仅供评审参考，不要原样泄露）：\n" + solution_summary)
        return "\n\n".join(pieces)

    def get_solution_brief(self, title_slug: str) -> str:
        if title_slug in self._solution_cache:
            return self._solution_cache[title_slug]
        try:
            raw = self.call_tool(
                "list_problem_solutions",
                {"questionSlug": title_slug, "limit": 3, "skip": 0, "orderBy": "HOT"},
            )
            solution_items = self._extract_solution_items(raw)
            if not solution_items:
                return ""
            first = solution_items[0]
            topic_id = self._first_value(first, ["topicId", "id"])
            slug = self._first_value(first, ["slug"])
            if topic_id:
                solution_raw = self.call_tool("get_problem_solution", {"topicId": str(topic_id)})
            elif slug:
                solution_raw = self.call_tool("get_problem_solution", {"slug": str(slug)})
            else:
                return self._summarize_text(json.dumps(first, ensure_ascii=False))
            summary = self._summarize_text(json.dumps(solution_raw, ensure_ascii=False))
            self._solution_cache[title_slug] = summary
            return summary
        except Exception as exc:
            logger.warning("LeetCode MCP solution lookup failed: %s", exc)
            return ""

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name not in PUBLIC_LEETCODE_MCP_TOOLS:
            raise ValueError(f"Refusing to call non-public LeetCode MCP tool: {tool_name}")
        return self._run(self._call_tool_async(tool_name, arguments))

    async def _list_tools_async(self) -> list[dict[str, Any]]:
        from hello_agents.protocols.mcp.client import MCPClient

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            async with MCPClient(self.server_config()) as client:
                return await client.list_tools()

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        from hello_agents.protocols.mcp.client import MCPClient

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            async with MCPClient(self.server_config()) as client:
                return await client.call_tool(tool_name, arguments)

    def _run(self, coro):
        async def with_timeout():
            return await asyncio.wait_for(coro, timeout=self.config.leetcode_mcp_tool_timeout_seconds)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(with_timeout())

        import concurrent.futures

        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(with_timeout())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(run_in_thread).result(timeout=self.config.leetcode_mcp_tool_timeout_seconds)

    def _problem_from_search_item(self, item: dict[str, Any]) -> LeetCodeProblem:
        title_slug = str(self._first_value(item, ["titleSlug", "title_slug", "slug"]) or "")
        tags = self._tags_from_item(item)
        difficulty = str(self._first_value(item, ["difficulty"]) or "")
        return LeetCodeProblem(
            frontend_question_id=str(self._first_value(item, ["frontendQuestionId", "questionFrontendId", "questionId", "id"]) or ""),
            title=str(self._first_value(item, ["title", "titleCn", "translatedTitle"]) or title_slug),
            title_slug=title_slug,
            difficulty=difficulty,
            ac_rate=float(self._first_value(item, ["acRate", "ac_rate", "acceptanceRate"]) or 0),
            paid_only=bool(self._first_value(item, ["paidOnly", "isPaidOnly"]) or False),
            topic_tags=[tag[0] for tag in tags],
            topic_names=[tag[1] for tag in tags],
            url=self._problem_url(title_slug),
        )

    def _problem_from_detail(self, raw: Any, fallback_slug: str) -> LeetCodeProblem | None:
        item = self._extract_detail_item(raw)
        if not item:
            return None
        problem = self._problem_from_search_item({**item, "titleSlug": self._first_value(item, ["titleSlug", "slug"]) or fallback_slug})
        problem.content = self._problem_content(item)
        problem.examples = self._extract_examples(problem.content)
        problem.constraints = self._extract_constraints(problem.content)
        return problem

    def _extract_problem_items(self, raw: Any) -> list[dict[str, Any]]:
        data = self._normalize_payload(raw)
        candidates = self._find_lists(data)
        for items in candidates:
            dict_items = [item for item in items if isinstance(item, dict)]
            if dict_items and any(self._first_value(item, ["titleSlug", "title_slug", "slug"]) for item in dict_items):
                return dict_items
        if isinstance(data, dict) and self._first_value(data, ["titleSlug", "title_slug", "slug"]):
            return [data]
        return []

    def _extract_detail_item(self, raw: Any) -> dict[str, Any] | None:
        data = self._normalize_payload(raw)
        if isinstance(data, dict):
            for key in ("question", "problem", "data"):
                value = data.get(key)
                if isinstance(value, dict):
                    return value
            return data
        return None

    def _extract_solution_items(self, raw: Any) -> list[dict[str, Any]]:
        data = self._normalize_payload(raw)
        for items in self._find_lists(data):
            dict_items = [item for item in items if isinstance(item, dict)]
            if dict_items and any(self._first_value(item, ["topicId", "id", "slug"]) for item in dict_items):
                return dict_items
        return []

    def _normalize_payload(self, raw: Any) -> Any:
        if isinstance(raw, str):
            text = raw.strip()
            for _ in range(3):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    return text
                if isinstance(parsed, str):
                    text = parsed
                    continue
                return parsed
            return text
        if isinstance(raw, list) and len(raw) == 1:
            return self._normalize_payload(raw[0])
        if isinstance(raw, dict):
            if "content" in raw and isinstance(raw["content"], list):
                texts = []
                for item in raw["content"]:
                    if isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                if texts:
                    return self._normalize_payload("\n".join(str(text) for text in texts))
            if "text" in raw:
                return self._normalize_payload(raw["text"])
        return raw

    def _find_lists(self, data: Any) -> list[list[Any]]:
        found: list[list[Any]] = []
        if isinstance(data, list):
            found.append(data)
            for item in data:
                found.extend(self._find_lists(item))
        elif isinstance(data, dict):
            for value in data.values():
                found.extend(self._find_lists(value))
        return found

    @staticmethod
    def _first_value(item: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
        return None

    @staticmethod
    def _tags_from_item(item: dict[str, Any]) -> list[tuple[str, str]]:
        raw_tags = item.get("topicTags") or item.get("tags") or item.get("topic_tags") or []
        tags: list[tuple[str, str]] = []
        if isinstance(raw_tags, list):
            for tag in raw_tags:
                if isinstance(tag, dict):
                    slug = str(tag.get("slug") or tag.get("name") or "")
                    name = str(tag.get("name") or slug)
                    if slug:
                        tags.append((slug, name))
                elif isinstance(tag, str):
                    tags.append((tag, tag))
        return tags

    def _problem_url(self, title_slug: str) -> str:
        if not title_slug:
            return ""
        return f"{self.config.leetcode_problem_url_base.rstrip('/')}/{title_slug}/"

    def _args_with_site(self, args: list[str]) -> list[str]:
        site = (self.config.leetcode_site or "cn").strip().lower()
        if site not in {"cn", "global"}:
            site = "cn"
        normalized = list(args)
        for flag in ("--site", "-s"):
            if flag in normalized:
                index = normalized.index(flag)
                if index + 1 < len(normalized):
                    normalized[index + 1] = site
                    return normalized
        normalized.extend(["--site", site])
        return normalized

    def _problem_content(self, item: dict[str, Any]) -> str:
        keys = ["translatedContent", "content", "description"]
        if (self.config.leetcode_site or "cn").lower() != "cn":
            keys = ["content", "translatedContent", "description"]
        for key in keys:
            value = self._first_value(item, [key])
            if not value:
                continue
            content = self._strip_html(str(value))
            if content and not self._is_unavailable_description(content):
                return content
        return ""

    @staticmethod
    def _strip_html(text: str) -> str:
        text = re.sub(r"<pre>(.*?)</pre>", lambda m: "\n" + m.group(1) + "\n", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = (
            text.replace("&nbsp;", " ")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _is_unavailable_description(text: str) -> bool:
        lowered = text.lower()
        return any(
            marker in lowered
            for marker in (
                "english description is not available",
                "please switch to chinese",
                "switch to chinese",
            )
        )

    @staticmethod
    def _extract_examples(text: str) -> list[str]:
        matches = re.findall(
            r"((?:Example|示例)\s*\d*\s*[:：].*?)(?=(?:Example|示例)\s*\d*\s*[:：]|Constraints?\s*[:：]|提示\s*[:：]|$)",
            text,
            flags=re.IGNORECASE,
        )
        return [re.sub(r"\s+", " ", item).strip()[:500] for item in matches]

    @staticmethod
    def _extract_constraints(text: str) -> list[str]:
        match = re.search(r"(?:Constraints?|提示)\s*[:：]\s*(.*)$", text, flags=re.IGNORECASE)
        if not match:
            return []
        raw = match.group(1)
        pieces = re.split(r"\s{2,}|;|\n|•|- ", raw)
        return [piece.strip() for piece in pieces if piece.strip()][:10]

    @staticmethod
    def _summarize_text(text: str, limit: int = 1200) -> str:
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."
