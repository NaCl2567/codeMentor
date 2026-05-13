# models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import json


# ------------------------------------------------------------------
# 基础组件：知识点
# ------------------------------------------------------------------
@dataclass
class KnowledgePoint:
    """知识点实体，可表示技能树中的一个节点。"""
    id: str
    name: str
    category: str               # 如 'Python', '算法', '安全'
    difficulty: int             # 1-10
    prerequisites: list[str] = field(default_factory=list)   # 前置知识点 id
    resources: list[str] = field(default_factory=list)       # 推荐学习资源链接


# ------------------------------------------------------------------
# 用户画像
# ------------------------------------------------------------------
@dataclass
class UserProfile:
    """学习者画像，记录当前能力与目标。"""
    user_id: str
    goal: str = ""                                      # 目标岗位或方向，如 'Python 数据分析师'
    current_level: str = "beginner"                     # beginner, intermediate, advanced
    mastered_skills: list[str] = field(default_factory=list)     # 已掌握知识点 id
    weak_skills: list[str] = field(default_factory=list)        # 薄弱知识点 id
    preferred_language: str = "Python"
    available_hours_per_week: int = 5
    learning_style: str = "mixed"                       # video, reading, project, mixed

    def summary(self) -> str:
        """生成用于 prompt 的简要描述。"""
        return (
            f"用户 {self.user_id}，目标：{self.goal}，当前水平：{self.current_level}，"
            f"已掌握：{', '.join(self.mastered_skills) or '无'}，"
            f"薄弱点：{', '.join(self.weak_skills) or '未知'}，"
            f"每周可投入 {self.available_hours_per_week} 小时"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "goal": self.goal,
            "current_level": self.current_level,
            "mastered_skills": self.mastered_skills,
            "weak_skills": self.weak_skills,
            "preferred_language": self.preferred_language,
            "available_hours_per_week": self.available_hours_per_week,
            "learning_style": self.learning_style,
        }


# ------------------------------------------------------------------
# 练习题目
# ------------------------------------------------------------------
@dataclass
class Exercise:
    """编程练习题实体。"""
    title: str
    language: str
    difficulty: str                     # 入门 / 基础 / 进阶 / 挑战
    tags: list[str] = field(default_factory=list)       # 涉及知识点
    description: str = ""
    input_format: str = ""
    output_format: str = ""
    example: str = ""
    starter_code: str = ""
    test_cases: list[dict[str, Any]] = field(default_factory=list)  # 隐藏的测试用例
    id: str = ""                        # 可选，题库 ID

    def to_markdown(self) -> str:
        """转换为 Markdown 格式展示给用户。"""
        md = f"## 练习题目：{self.title}\n"
        md += f"**语言**：{self.language}\n"
        md += f"**难度**：{self.difficulty}\n"
        md += f"**知识点**：{', '.join(self.tags)}\n\n"
        if self.description:
            md += f"### 问题描述\n{self.description}\n\n"
        if self.input_format:
            md += f"### 输入格式\n{self.input_format}\n\n"
        if self.output_format:
            md += f"### 输出格式\n{self.output_format}\n\n"
        if self.example:
            md += f"### 示例\n{self.example}\n\n"
        if self.starter_code:
            md += f"### 起始代码\n```{self.language}\n{self.starter_code}\n```\n"
        return md

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "language": self.language,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "description": self.description,
            "input_format": self.input_format,
            "output_format": self.output_format,
            "example": self.example,
            "starter_code": self.starter_code,
            "test_cases": self.test_cases,
        }


# ------------------------------------------------------------------
# 代码审查报告
# ------------------------------------------------------------------
@dataclass
class ReviewReport:
    """代码审查的结构化报告。"""
    code: str                           # 原始代码
    language: str
    overall_score: float                # 0-10
    lines: int
    critical_issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    performance_issues: list[str] = field(default_factory=list)
    security_issues: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)          # 优秀实践
    improved_code: str = ""
    related_knowledge: list[str] = field(default_factory=list)   # 关联知识点 ID
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def markdown(self) -> str:
        """生成 Markdown 格式的审查报告。"""
        md = f"## 代码审查报告\n"
        md += f"**审查时间**：{self.timestamp}\n"
        md += f"**整体评分**：{self.overall_score}/10\n"
        md += f"**代码行数**：{self.lines}\n\n"

        if self.critical_issues:
            md += "### 严重问题\n" + "\n".join(f"- {item}" for item in self.critical_issues) + "\n\n"
        if self.suggestions:
            md += "### 改进建议\n" + "\n".join(f"- {item}" for item in self.suggestions) + "\n\n"
        if self.performance_issues:
            md += "### 性能优化\n" + "\n".join(f"- {item}" for item in self.performance_issues) + "\n\n"
        if self.security_issues:
            md += "### 安全风险\n" + "\n".join(f"- {item}" for item in self.security_issues) + "\n\n"
        if self.highlights:
            md += "### 优秀实践\n" + "\n".join(f"- {item}" for item in self.highlights) + "\n\n"
        if self.improved_code:
            md += f"### 改进后示例\n```{self.language}\n{self.improved_code}\n```\n\n"
        if self.related_knowledge:
            md += "### 关联知识点\n" + "\n".join(f"- {kp}" for kp in self.related_knowledge) + "\n"

        return md

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "language": self.language,
            "overall_score": self.overall_score,
            "lines": self.lines,
            "critical_issues": self.critical_issues,
            "suggestions": self.suggestions,
            "performance_issues": self.performance_issues,
            "security_issues": self.security_issues,
            "highlights": self.highlights,
            "improved_code": self.improved_code,
            "related_knowledge": self.related_knowledge,
        }


# ------------------------------------------------------------------
# 学习路径
# ------------------------------------------------------------------
@dataclass
class LearningStage:
    """学习路径中的一个阶段。"""
    stage_id: int
    topic: str
    objectives: str
    estimated_weeks: int
    milestone_project: str = ""
    resources: list[str] = field(default_factory=list)        # 推荐资源
    weekly_plan: list[str] = field(default_factory=list)      # 每周安排
    checkpoint: str = ""                                      # 检查点任务


@dataclass
class LearningPath:
    """完整的学习路径规划。"""
    goal: str
    user_id: str
    total_weeks: int
    current_stage_index: int = 0      # 当前执行到的阶段索引
    stages: list[LearningStage] = field(default_factory=list)

    def render(self) -> str:
        """以 Markdown 格式渲染完整路径（含所有阶段概览）。"""
        md = f"## 学习路径规划：{self.goal}\n"
        md += f"**适用对象**：{self.user_id}\n"
        md += f"**预计总时长**：{self.total_weeks} 周\n\n"

        md += "### 阶段概览\n"
        md += "| 阶段 | 主题 | 目标 | 预计耗时 | 里程碑项目 |\n"
        md += "|------|------|------|----------|------------|\n"
        for stage in self.stages:
            md += f"| {stage.stage_id} | {stage.topic} | {stage.objectives} | {stage.estimated_weeks}周 | {stage.milestone_project} |\n"

        # 如果正在细化某个阶段，可展示当前阶段详情
        if 0 <= self.current_stage_index < len(self.stages):
            stage = self.stages[self.current_stage_index]
            md += f"\n### 当前阶段 {stage.stage_id}：{stage.topic}\n"
            md += f"**学习目标**：{stage.objectives}\n\n"
            if stage.resources:
                md += "**推荐资源**：\n" + "\n".join(f"- {r}" for r in stage.resources) + "\n\n"
            if stage.weekly_plan:
                md += "**每周安排**：\n" + "\n".join(f"- {w}" for w in stage.weekly_plan) + "\n\n"
            if stage.checkpoint:
                md += f"**检查点**：{stage.checkpoint}\n"

        return md

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "user_id": self.user_id,
            "total_weeks": self.total_weeks,
            "current_stage_index": self.current_stage_index,
            "stages": [
                {
                    "stage_id": s.stage_id,
                    "topic": s.topic,
                    "objectives": s.objectives,
                    "estimated_weeks": s.estimated_weeks,
                    "milestone_project": s.milestone_project,
                    "resources": s.resources,
                    "weekly_plan": s.weekly_plan,
                    "checkpoint": s.checkpoint,
                }
                for s in self.stages
            ],
        }


# ------------------------------------------------------------------
# 对话状态
# ------------------------------------------------------------------
@dataclass
class TutorState:
    """
    一个用户会话的完整状态，贯穿一次多轮交互。
    包含用户画像、对话历史、当前练习与审查上下文、学习路径快照等。
    """
    user_id: str
    user_profile: UserProfile = field(default_factory=lambda: UserProfile(user_id=""))
    conversation_history: list[dict[str, str]] = field(default_factory=list)  # [{"role": "user/assistant", "content": ...}]
    
    # 当前活动上下文
    active_exercise: Optional[Exercise] = None
    last_review_report: Optional[ReviewReport] = None
    active_learning_path: Optional[LearningPath] = None

    def __post_init__(self):
        # 保证 user_profile 中的 user_id 与 state 的 user_id 一致
        if not self.user_profile.user_id:
            self.user_profile.user_id = self.user_id

    def add_interaction(self, user_msg: str, assistant_msg: str) -> None:
        """记录一轮对话。"""
        self.conversation_history.append({"role": "user", "content": user_msg})
        self.conversation_history.append({"role": "assistant", "content": assistant_msg})
        # 可选：控制历史长度
        max_turns = 10  # 可通过配置调整
        if len(self.conversation_history) > max_turns * 2:
            self.conversation_history = self.conversation_history[-(max_turns * 2):]

    def recent_history(self, limit: int = 5) -> str:
        """获取最近 N 轮对话的文本表示，用于注入 prompt。"""
        lines = []
        for entry in self.conversation_history[-limit * 2:]:
            role = "用户" if entry["role"] == "user" else "助手"
            lines.append(f"{role}：{entry['content']}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_profile": self.user_profile.to_dict(),
            "conversation_history": self.conversation_history,
            "active_exercise": self.active_exercise.to_dict() if self.active_exercise else None,
            "last_review_report": self.last_review_report.to_dict() if self.last_review_report else None,
            "active_learning_path": self.active_learning_path.to_dict() if self.active_learning_path else None,
        }