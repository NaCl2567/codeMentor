from __future__ import annotations

import logging
import re
from typing import Any

from ..config import TutorConfig

logger = logging.getLogger(__name__)


class LeetCodeService:
    """辅助工具类，提供基于标签的解题思路、复杂度预估、审查重点等后处理能力。

    选题决策已交由 agent 通过 LeetCode MCP 工具自主完成，此类仅保留
    硬编码的标签→建议映射，作为次要参考依据。
    """

    def __init__(self, config: TutorConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # 公开工具方法（基于标签的固定建议映射）
    # ------------------------------------------------------------------

    @staticmethod
    def reference_solution_brief(tags: list[str]) -> str:
        """根据题目标签返回解题思路提示。"""
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
    def expected_complexity(tags: list[str]) -> str:
        """根据题目标签预估期望时间/空间复杂度。"""
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
    def review_focus(tags: list[str]) -> list[str]:
        """根据题目标签返回代码审查时应重点关注的方向。"""
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

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _display_difficulty(difficulty: str) -> str:
        mapping = {"EASY": "基础", "MEDIUM": "进阶", "HARD": "挑战"}
        return mapping.get(difficulty.upper(), difficulty)

    @staticmethod
    def _clean_keyword(value: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", value)
        return " ".join(words[:6])
