from __future__ import annotations

import json
from typing import Any

from hello_agents.tools.base import Tool, ToolParameter

from ..config import TutorConfig
from .leetcode_mcp_client import LeetCodeMCPClient


class LeetCodeMCPPublicTool(Tool):
    def __init__(self, *, name: str, description: str, parameters: list[ToolParameter], tool_name: str, config: TutorConfig):
        super().__init__(name=name, description=description)
        self._parameters = parameters
        self._tool_name = tool_name
        self._client = LeetCodeMCPClient(config)

    def run(self, parameters: dict[str, Any]) -> str:
        args = self._normalize_args(parameters)
        try:
            result = self._client.call_tool(self._tool_name, args)
        except Exception as exc:
            return f"LeetCode MCP tool '{self._tool_name}' failed: {exc}"
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_parameters(self) -> list[ToolParameter]:
        return self._parameters

    @staticmethod
    def _normalize_args(parameters: dict[str, Any]) -> dict[str, Any]:
        # Some agents pass the full JSON object as {"input": "..."}.
        if set(parameters.keys()) == {"input"} and isinstance(parameters["input"], str):
            try:
                parsed = json.loads(parameters["input"])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"keyword": parameters["input"]}
        args = dict(parameters)
        if isinstance(args.get("tags"), str):
            args["tags"] = [tag.strip() for tag in args["tags"].split(",") if tag.strip()]
        for key in ("limit", "skip"):
            if key in args and isinstance(args[key], str) and args[key].isdigit():
                args[key] = int(args[key])
        return args


def create_public_leetcode_mcp_tools(config: TutorConfig) -> list[Tool]:
    if not config.enable_leetcode_mcp or not config.expose_leetcode_mcp_tools_to_agents:
        return []

    return [
        LeetCodeMCPPublicTool(
            name="leetcode_mcp_search_problems",
            tool_name="search_problems",
            config=config,
            description="Search public LeetCode problems by keyword, difficulty, and tags. Does not require login.",
            parameters=[
                ToolParameter(name="searchKeywords", type="string", description="Search keywords, e.g. two sum or hash table.", required=False),
                ToolParameter(name="difficulty", type="string", description="Difficulty: EASY, MEDIUM, or HARD.", required=False),
                ToolParameter(name="tags", type="array", description="Topic tag slugs, e.g. array,hash-table.", required=False),
                ToolParameter(name="limit", type="integer", description="Max number of problems to return.", required=False, default=10),
            ],
        ),
        LeetCodeMCPPublicTool(
            name="leetcode_mcp_get_problem",
            tool_name="get_problem",
            config=config,
            description="Get public LeetCode problem details by titleSlug. Does not require login.",
            parameters=[
                ToolParameter(name="titleSlug", type="string", description="LeetCode title slug, e.g. two-sum.", required=True),
            ],
        ),
        LeetCodeMCPPublicTool(
            name="leetcode_mcp_list_problem_solutions",
            tool_name="list_problem_solutions",
            config=config,
            description="List public solution articles for a LeetCode problem. Does not require login.",
            parameters=[
                ToolParameter(name="questionSlug", type="string", description="LeetCode question slug, e.g. two-sum.", required=True),
                ToolParameter(name="limit", type="integer", description="Max number of solution articles.", required=False, default=3),
                ToolParameter(name="skip", type="integer", description="Pagination offset.", required=False, default=0),
                ToolParameter(name="orderBy", type="string", description="Ordering, e.g. HOT or MOST_RECENT.", required=False, default="HOT"),
            ],
        ),
        LeetCodeMCPPublicTool(
            name="leetcode_mcp_get_problem_solution",
            tool_name="get_problem_solution",
            config=config,
            description="Get one public solution article by topicId or slug. Does not require login.",
            parameters=[
                ToolParameter(name="topicId", type="string", description="Solution topic id.", required=False),
                ToolParameter(name="slug", type="string", description="Solution article slug.", required=False),
            ],
        ),
    ]
