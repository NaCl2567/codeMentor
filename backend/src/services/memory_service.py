from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from datetime import datetime

from hello_agents.memory import MemoryConfig
from hello_agents.tools.builtin.memory_tool import MemoryTool
from hello_agents.tools.builtin.note_tool import NoteTool

from ..config import TutorConfig
from ..models import (
    Exercise,
    ExerciseMemory,
    ReviewMemory,
    ReviewReport,
    SkillMemory,
    TutorState,
    UserLongTermMemory,
)

logger = logging.getLogger(__name__)


TOPIC_ALIASES = {
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
    "complexity-analysis": ["复杂度", "时间复杂度", "空间复杂度", "o(n", "性能"],
    "edge-cases": ["边界", "空输入", "空列表", "特殊情况", "越界"],
    "code-style": ["命名", "可读性", "注释", "风格"],
}

LANGUAGE_ALIASES = {
    "Python": ["python", "py"],
    "JavaScript": ["javascript", "js", "前端"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java"],
    "C++": ["c++", "cpp"],
    "Go": ["go", "golang"],
}

DIFFICULTY_ALIASES = {
    "入门": ["入门", "简单", "easy"],
    "基础": ["基础"],
    "进阶": ["进阶", "中等", "medium"],
    "挑战": ["挑战", "困难", "hard"],
}

STYLE_ALIASES = {
    "video": ["视频", "课程"],
    "reading": ["文档", "文章", "阅读"],
    "project": ["项目", "实战", "工程"],
    "example_first": ["例子", "示例", "案例"],
    "step_by_step": ["一步步", "详细", "拆解"],
    "concise": ["简洁", "直接"],
    "chinese": ["中文"],
}

ERROR_PATTERNS = {
    "missing_edge_case": ["边界", "空输入", "越界", "特殊情况"],
    "wrong_complexity": ["复杂度", "性能", "o(n^2", "低效", "双重循环"],
    "hash_map_issue": ["哈希", "hash", "字典", "key", "重复元素"],
    "pointer_movement_issue": ["指针", "窗口", "left", "right"],
    "binary_search_boundary": ["二分", "边界", "mid"],
    "dp_state_issue": ["dp", "动态规划", "状态", "转移"],
    "code_style_issue": ["命名", "可读性", "注释", "风格"],
    "security_issue": ["安全", "注入", "xss", "secret", "密钥"],
}


class MemoryService:
    """Extract and persist user long-term memory from tutor interactions."""

    def __init__(self, config: TutorConfig, note_tool: NoteTool | None = None) -> None:
        self.config = config
        self.store_path = Path(config.memory_store_path)
        self.note_tool = note_tool
        if self.note_tool is None and config.enable_notes:
            self.note_tool = NoteTool(workspace=config.notes_workspace)
        self._memory_tools: dict[str, MemoryTool] = {}
        self._memory_tool_failed_users: set[str] = set()

    def load_user_memory(self, user_id: str) -> UserLongTermMemory:
        note_memory = self._load_memory_from_note(user_id)
        if note_memory:
            self._seed_memory_tool(note_memory)
            return note_memory

        # Legacy fallback for existing JSON memories from the first implementation.
        data = self._read_store()
        raw = data.get(user_id)
        if not raw:
            return UserLongTermMemory(user_id=user_id)
        try:
            memory = UserLongTermMemory.model_validate(raw)
            self._seed_memory_tool(memory)
            return memory
        except Exception as exc:
            logger.warning("Failed to parse memory for user %s, creating fresh memory: %s", user_id, exc)
            return UserLongTermMemory(user_id=user_id)

    def save_user_memory(self, memory: UserLongTermMemory) -> None:
        if not self.config.enable_memory:
            return
        memory.touch()
        self._save_memory_to_note(memory)
        self._seed_memory_tool(memory)

    def hydrate_state(self, state: TutorState) -> None:
        """Apply persisted memory back into the lightweight runtime profile."""
        if not self.config.enable_memory:
            return
        memory = self.load_user_memory(state.user_id)
        state.user_profile.weak_skills = self._top_skills(memory, key="weak_count", limit=5)
        state.user_profile.mastered_skills = [
            skill.knowledge_id for skill in memory.skills.values() if skill.mastery_score >= 0.75
        ][:8]
        preferred_language = self._top_key(memory.preferences.preferred_languages)
        if preferred_language:
            state.user_profile.preferred_language = preferred_language
        preferred_style = self._top_key(memory.preferences.learning_style_signals)
        if preferred_style:
            state.user_profile.learning_style = preferred_style

    def record_interaction(
        self,
        state: TutorState,
        *,
        user_msg: str,
        assistant_msg: str,
        intent: str,
        params: dict[str, Any],
    ) -> UserLongTermMemory | None:
        if not self.config.enable_memory:
            return None

        memory = self.load_user_memory(state.user_id)
        self._record_request(memory, user_msg, params)
        self._extract_preferences(memory, user_msg, params)
        self._extract_focus_topics(memory, user_msg, params)

        if intent == "request_exercise" and state.active_exercise:
            self._record_exercise(memory, state.active_exercise)
        if intent == "submit_code" and state.last_review_report:
            self._record_review(memory, state.active_exercise, state.last_review_report)

        self._sync_profile_from_memory(state, memory)
        self.save_user_memory(memory)
        return memory

    def get_runtime_context(self, user_id: str, query: str, *, limit: int = 5) -> str:
        """Retrieve compact session memory through hello_agents MemoryTool."""
        if not self.config.enable_memory:
            return ""
        tool = self._get_memory_tool(user_id)
        if not tool:
            return ""
        result = tool.run(
            {
                "action": "search",
                "query": query,
                "memory_type": "working",
                "limit": limit,
                "min_importance": 0.1,
            }
        )
        if result.startswith("❌") or "未找到" in result:
            return ""
        return result

    def _get_memory_tool(self, user_id: str) -> MemoryTool | None:
        if user_id in self._memory_tool_failed_users:
            return None
        if user_id not in self._memory_tools:
            try:
                memory_config = MemoryConfig(
                    storage_path=str(self.store_path.parent),
                    working_memory_capacity=12,
                    working_memory_tokens=1200,
                    working_memory_ttl_minutes=240,
                )
                self._memory_tools[user_id] = MemoryTool(
                    user_id=user_id,
                    memory_config=memory_config,
                    memory_types=["working"],
                )
            except Exception as exc:
                logger.warning("Failed to initialize MemoryTool for user %s: %s", user_id, exc)
                self._memory_tool_failed_users.add(user_id)
                return None
        return self._memory_tools[user_id]

    def _seed_memory_tool(self, memory: UserLongTermMemory) -> None:
        """Put compact extracted facts into hello_agents MemoryTool for runtime retrieval."""
        tool = self._get_memory_tool(memory.user_id)
        if not tool:
            return
        tool.clear_session()
        facts = self._memory_facts(memory)
        for fact in facts:
            tool.run(
                {
                    "action": "add",
                    "content": fact,
                    "memory_type": "working",
                    "importance": 0.85,
                    "source": "long_term_memory_note",
                }
            )

    def _memory_facts(self, memory: UserLongTermMemory) -> list[str]:
        facts: list[str] = []
        if memory.preferences.preferred_languages:
            facts.append(f"用户偏好语言：{self._top_key(memory.preferences.preferred_languages)}")
        if memory.preferences.preferred_difficulties:
            facts.append(f"用户偏好难度：{self._top_key(memory.preferences.preferred_difficulties)}")
        if memory.preferences.learning_style_signals:
            facts.append(f"用户学习风格信号：{self._top_key(memory.preferences.learning_style_signals)}")
        weak = self._top_skills(memory, key="weak_count", limit=5)
        if weak:
            facts.append(f"用户薄弱点：{', '.join(weak)}")
        focus = self._top_skills(memory, key="focus_count", limit=5)
        if focus:
            facts.append(f"用户近期关注知识点：{', '.join(focus)}")
        if memory.exercise_history:
            latest = memory.exercise_history[-1]
            facts.append(f"用户最近练习：{latest.title}，标签：{', '.join(latest.tags)}")
        if memory.review_history:
            latest_review = memory.review_history[-1]
            facts.append(
                f"用户最近 Review 评分：{latest_review.score}/10，错误模式：{', '.join(latest_review.error_patterns) or '无'}"
            )
        return facts

    def _memory_note_title(self, user_id: str) -> str:
        return f"long_term_memory::{user_id}"

    def _find_memory_note_id(self, user_id: str) -> str:
        if not self.note_tool:
            return ""
        title = self._memory_note_title(user_id)
        for note in self.note_tool.notes_index.get("notes", []):
            tags = note.get("tags") or []
            if note.get("title") == title or ("long_term_memory" in tags and f"user:{user_id}" in tags):
                return str(note.get("id") or "")
        return ""

    def _load_memory_from_note(self, user_id: str) -> UserLongTermMemory | None:
        if not self.note_tool:
            return None
        note_id = self._find_memory_note_id(user_id)
        if not note_id:
            return None
        try:
            note_path = self.note_tool._get_note_path(note_id)
            markdown_text = note_path.read_text(encoding="utf-8")
            note = self.note_tool._markdown_to_note(markdown_text)
            payload = json.loads(note.get("content", "{}"))
            return UserLongTermMemory.model_validate(payload)
        except Exception as exc:
            logger.warning("Failed to load long-term memory note for user %s: %s", user_id, exc)
            return None

    def _save_memory_to_note(self, memory: UserLongTermMemory) -> None:
        if not self.note_tool:
            logger.warning("NoteTool is disabled; long-term memory for user %s was not persisted.", memory.user_id)
            return
        content = json.dumps(memory.to_dict(), ensure_ascii=False, indent=2)
        title = self._memory_note_title(memory.user_id)
        tags = ["long_term_memory", f"user:{memory.user_id}", "codetutor"]
        note_id = self._find_memory_note_id(memory.user_id)
        params = {
            "title": title,
            "content": content,
            "note_type": "reference",
            "tags": tags,
        }
        if note_id:
            params["action"] = "update"
            params["note_id"] = note_id
        else:
            params["action"] = "create"
        result = self.note_tool.run(params)
        if result.startswith("❌"):
            logger.warning("Failed to persist long-term memory via NoteTool: %s", result)

    def _read_store(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read memory store %s: %s", self.store_path, exc)
            return {}

    def _record_request(self, memory: UserLongTermMemory, user_msg: str, params: dict[str, Any]) -> None:
        text = user_msg.strip()
        if text:
            memory.recent_requests.append(text[:500])
            memory.recent_requests = memory.recent_requests[-20:]
        for key in ("topic", "context"):
            value = str(params.get(key) or "").strip()
            if value:
                self._bump(memory.preferences.requested_topics, value)

    def _extract_preferences(self, memory: UserLongTermMemory, user_msg: str, params: dict[str, Any]) -> None:
        text = f"{user_msg} {params}".lower()
        language = str(params.get("language") or "").strip()
        if language:
            self._bump(memory.preferences.preferred_languages, language)
        for canonical, aliases in LANGUAGE_ALIASES.items():
            if any(alias.lower() in text for alias in aliases):
                self._bump(memory.preferences.preferred_languages, canonical)

        difficulty = str(params.get("difficulty") or "").strip()
        if difficulty:
            self._bump(memory.preferences.preferred_difficulties, difficulty)
        for canonical, aliases in DIFFICULTY_ALIASES.items():
            if any(alias.lower() in text for alias in aliases):
                self._bump(memory.preferences.preferred_difficulties, canonical)

        for canonical, aliases in STYLE_ALIASES.items():
            if any(alias.lower() in text for alias in aliases):
                self._bump(memory.preferences.learning_style_signals, canonical)

        if "leetcode" in text or "力扣" in text:
            memory.preferences.prefers_leetcode = True

    def _extract_focus_topics(self, memory: UserLongTermMemory, user_msg: str, params: dict[str, Any]) -> None:
        combined = " ".join(
            [
                user_msg,
                str(params.get("topic") or ""),
                str(params.get("context") or ""),
                str(params.get("problem_description") or ""),
            ]
        ).lower()
        for topic in self._topics_from_text(combined):
            skill = self._get_skill(memory, topic)
            skill.focus_count += 1
            self._append_evidence(skill, f"用户请求关注：{self._short(user_msg)}")

    def _record_exercise(self, memory: UserLongTermMemory, exercise: Exercise) -> None:
        exercise_key = exercise.id or exercise.source_url or exercise.title
        if exercise_key and any(item.exercise_id == exercise_key for item in memory.exercise_history):
            return
        memory.exercise_history.append(
            ExerciseMemory(
                exercise_id=exercise_key,
                title=exercise.title,
                source=exercise.source,
                source_url=exercise.source_url,
                difficulty=exercise.difficulty,
                tags=exercise.tags,
            )
        )
        memory.exercise_history = memory.exercise_history[-100:]
        for tag in exercise.tags:
            skill = self._get_skill(memory, tag)
            skill.practice_count += 1
            skill.focus_count += 1
            skill.mastery_score = min(1.0, skill.mastery_score + 0.03)
            self._append_evidence(skill, f"练习题：{exercise.title}")

    def _record_review(
        self, memory: UserLongTermMemory, active_exercise: Exercise | None, report: ReviewReport
    ) -> None:
        exercise_tags = active_exercise.tags if active_exercise else []
        related = list(dict.fromkeys([*exercise_tags, *report.related_knowledge]))
        issue_text = " ".join(
            [
                *report.critical_issues,
                *report.suggestions,
                *report.performance_issues,
                *report.security_issues,
            ]
        )
        patterns = self._error_patterns(issue_text)
        inferred_topics = self._topics_from_text(issue_text)
        knowledge = list(dict.fromkeys([*related, *inferred_topics]))

        memory.review_history.append(
            ReviewMemory(
                exercise_title=active_exercise.title if active_exercise else "",
                exercise_id=(active_exercise.id or active_exercise.source_url) if active_exercise else "",
                score=report.overall_score,
                related_knowledge=knowledge,
                error_patterns=patterns,
            )
        )
        memory.review_history = memory.review_history[-100:]

        weak_delta = 1 if report.overall_score < 7 else 0
        for topic in knowledge:
            skill = self._get_skill(memory, topic)
            skill.review_count += 1
            if weak_delta or topic in inferred_topics:
                skill.weak_count += 1
                skill.mastery_score = max(0.0, skill.mastery_score - 0.04)
                self._append_evidence(skill, f"Review 暴露问题：{self._short(issue_text)}")
            elif report.overall_score >= 8:
                skill.mastery_score = min(1.0, skill.mastery_score + 0.05)
                self._append_evidence(skill, f"Review 表现较好，评分 {report.overall_score}/10")

        for pattern in patterns:
            skill = self._get_skill(memory, pattern)
            skill.weak_count += 1
            skill.review_count += 1
            self._append_evidence(skill, f"错误模式：{pattern}")

    def _sync_profile_from_memory(self, state: TutorState, memory: UserLongTermMemory) -> None:
        state.user_profile.weak_skills = self._top_skills(memory, key="weak_count", limit=5)
        state.user_profile.mastered_skills = [
            skill.knowledge_id
            for skill in sorted(memory.skills.values(), key=lambda item: item.mastery_score, reverse=True)
            if skill.mastery_score >= 0.75
        ][:8]
        language = self._top_key(memory.preferences.preferred_languages)
        if language:
            state.user_profile.preferred_language = language
        style = self._top_key(memory.preferences.learning_style_signals)
        if style:
            state.user_profile.learning_style = style

    def _topics_from_text(self, text: str) -> list[str]:
        topics = []
        lowered = text.lower()
        for canonical, aliases in TOPIC_ALIASES.items():
            if any(alias.lower() in lowered for alias in aliases):
                topics.append(canonical)
        return topics

    def _error_patterns(self, text: str) -> list[str]:
        lowered = text.lower()
        patterns = []
        for canonical, aliases in ERROR_PATTERNS.items():
            if any(alias.lower() in lowered for alias in aliases):
                patterns.append(canonical)
        return patterns

    def _get_skill(self, memory: UserLongTermMemory, knowledge_id: str) -> SkillMemory:
        if knowledge_id not in memory.skills:
            memory.skills[knowledge_id] = SkillMemory(knowledge_id=knowledge_id)
        skill = memory.skills[knowledge_id]
        skill.last_seen_at = datetime.now().isoformat()
        return skill

    @staticmethod
    def _append_evidence(skill: SkillMemory, item: str) -> None:
        if item:
            skill.evidence.append(item)
            skill.evidence = skill.evidence[-8:]

    @staticmethod
    def _bump(counter: dict[str, int], key: str) -> None:
        if not key:
            return
        counter[key] = counter.get(key, 0) + 1

    @staticmethod
    def _top_key(counter: dict[str, int]) -> str:
        if not counter:
            return ""
        return max(counter.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _top_skills(memory: UserLongTermMemory, *, key: str, limit: int) -> list[str]:
        skills = sorted(
            memory.skills.values(),
            key=lambda item: (getattr(item, key), item.focus_count + item.review_count),
            reverse=True,
        )
        return [skill.knowledge_id for skill in skills if getattr(skill, key) > 0][:limit]

    @staticmethod
    def _short(text: str, limit: int = 120) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."
