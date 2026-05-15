from __future__ import annotations
import logging
import re
from typing import Any, Iterator

from hello_agents import ToolAwareSimpleAgent
from ..config import TutorConfig
from ..models import TutorState, LearningPath, LearningStage
from ..prompt_utils import safe_format_prompt
from ..prompts import path_planner_prompt
logger = logging.getLogger(__name__)

class PathService:
    """封装学习路径规划 Agent 的调用与结果解析。"""

    def __init__(self, planner_agent: ToolAwareSimpleAgent, config: TutorConfig) -> None:
        self.agent = planner_agent
        self.config = config

    def plan_path(self, state: TutorState, params: dict) -> LearningPath:
        """
        生成初始学习路径（Plan 模式），返回 LearningPath 对象。
        params 可选 "goal"（目标岗位）等，缺失时使用用户画像中的值。
        """
        goal = params.get("goal") or state.user_profile.goal or "通用编程提升"
        state.user_profile.goal = goal
        prompt = self._build_prompt(state, goal)
        raw_response = self.agent.run(prompt)
        path = self._parse_plan(raw_response, state.user_id, goal)
        state.active_learning_path = path
        return path

    def plan_path_stream(self, state: TutorState, params: dict) -> Iterator[dict[str, Any]]:
        """
        流式生成学习路径，实时输出 chunk，最后产出完整的 LearningPath。
        """
        goal = params.get("goal") or state.user_profile.goal or "通用编程提升"
        state.user_profile.goal = goal
        prompt = self._build_prompt(state, goal)

        collected_chunks: list[str] = []
        for chunk in self.agent.stream_run(prompt):
            if chunk:
                collected_chunks.append(chunk)
                yield {"type": "path_chunk", "content": chunk}

        full_response = "".join(collected_chunks)
        path = self._parse_plan(full_response, state.user_id, goal)
        state.active_learning_path = path
        yield {"type": "learning_path", "path": path}

    def _build_prompt(self, state: TutorState, goal: str) -> str:
        """构建填充用户画像与对话历史的完整提示词。"""
        user_profile_text = state.user_profile.summary()
        history_text = state.recent_history(limit=5)
        active_exercise = state.active_exercise.to_markdown() if state.active_exercise else "无"
        last_review = state.last_review_report.markdown if state.last_review_report else "无"
        active_path = state.active_learning_path.render() if state.active_learning_path else "无"

        prompt = safe_format_prompt(
            path_planner_prompt,
            goal=goal,
            current_level=state.user_profile.current_level,
            user_profile=user_profile_text,
            history=history_text,
            active_exercise=active_exercise,
            last_review=last_review,
            active_path=active_path,
        )
        return prompt

    def _parse_plan(self, raw_markdown: str, user_id: str, goal: str) -> LearningPath:
        """
        从 Plan 输出的 Markdown 表格中提取阶段列表，构建 LearningPath。
        """
        # 提取总周数
        total_weeks = 0
        weeks_match = re.search(r"预计总时长[：:]\s*(\d+)\s*周", raw_markdown)
        if weeks_match:
            total_weeks = int(weeks_match.group(1))

        # 定位表格开始行
        lines = raw_markdown.splitlines()
        table_start = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("| 阶段 |") or line.strip().startswith("|阶段|"):
                table_start = i
                break
        if table_start == -1:
            # 未找到表格，返回空路径
            return LearningPath(goal=goal, user_id=user_id, total_weeks=total_weeks)

        # 跳过表头与分隔线
        data_lines = lines[table_start + 2:]  # 跳过表头和分隔行
        stages: list[LearningStage] = []
        for line in data_lines:
            line = line.strip()
            if not line.startswith("|"):
                break   # 表格结束
            parts = [p.strip() for p in line.split("|")[1:-1]]  # 去掉首尾空
            if len(parts) < 5:
                continue
            try:
                stage_id = int(parts[0])
            except ValueError:
                continue  # 非数据行
            topic = parts[1]
            objectives = parts[2]
            weeks_str = parts[3].replace("周", "").strip()
            try:
                weeks = int(weeks_str)
            except ValueError:
                weeks = 0
            milestone = parts[4]

            stage = LearningStage(
                stage_id=stage_id,
                topic=topic,
                objectives=objectives,
                estimated_weeks=weeks,
                milestone_project=milestone,
                # 细化信息在 Plan 阶段暂不填充，留待后续 Solve 步骤补充
                resources=[],
                weekly_plan=[],
                checkpoint="",
            )
            stages.append(stage)

        path = LearningPath(
            goal=goal,
            user_id=user_id,
            total_weeks=total_weeks,
            stages=stages,
            current_stage_index=0,
        )
        return path
