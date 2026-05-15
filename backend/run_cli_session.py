from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def print_banner(provider: str, model: str, user_id: str) -> None:
    print("=" * 72)
    print("CodeTutorAgent CLI 会话")
    print(f"provider={provider or '(default)'}  model={model or '(default)'}  user_id={user_id}")
    print("输入 /help 查看命令，输入 /exit 结束会话。")
    print("=" * 72)


def print_help() -> None:
    print(
        """
可用命令:
  /help        显示帮助
  /state       显示当前会话状态摘要
  /history     显示最近对话历史
  /exit        退出

示例输入:
  给我一题 Python 列表基础练习
  请 review 这段代码：
  ```python
  def add(a, b):
      return a - b
  ```
  我想成为 Python 后端工程师，给我学习路径
""".strip()
    )


def run_one_turn(tutor, user_id: str, message: str, show_intent: bool) -> None:
    state = tutor._get_or_create_state(user_id)
    if show_intent:
        intent, params = tutor._classify_intent(state, message)
        print(f"\n[Intent] {intent}")
        print(f"[Params] {params}")
        response = tutor.chat_with_intent(user_id, message, intent, params)
    else:
        response = tutor.chat(user_id, message)
    print("\n[导师]")
    print(response)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a command-line CodeTutorAgent session.")
    parser.add_argument("--user-id", default="cli_user", help="Session user id.")
    parser.add_argument("--once", help="Run one message and exit.")
    parser.add_argument(
        "--show-intent",
        action="store_true",
        help="Print classified intent and params before the final response.",
    )
    parser.add_argument(
        "--enable-notes",
        action="store_true",
        help="Enable NoteTool if configured. Disabled by default for cleaner CLI testing.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    env_file = repo_root / "backend" / ".env"
    load_env_file(env_file)
    sys.path.insert(0, str(repo_root))

    try:
        from backend.src.agent import CodeTutorAgent
        from backend.src.config import TutorConfig
    except Exception:
        print("[FAIL] import failed")
        print(traceback.format_exc())
        return 1

    try:
        cfg = TutorConfig.from_env()
        if not args.enable_notes:
            cfg.enable_notes = False
        tutor = CodeTutorAgent(cfg)
    except Exception:
        print("[FAIL] CodeTutorAgent init failed")
        print(traceback.format_exc())
        return 1

    print_banner(cfg.llm_provider, cfg.llm_model_id, args.user_id)

    if args.once:
        try:
            run_one_turn(tutor, args.user_id, args.once, args.show_intent)
            return 0
        except Exception:
            print("[FAIL] one-turn session failed")
            print(traceback.format_exc())
            return 2

    print_help()
    while True:
        try:
            message = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] 会话结束。")
            return 0

        if not message:
            continue
        if message in {"/exit", "/quit", "exit", "quit"}:
            print("[INFO] 会话结束。")
            return 0
        if message == "/help":
            print_help()
            continue
        if message == "/state":
            state = tutor._get_or_create_state(args.user_id)
            print(state.to_dict())
            continue
        if message == "/history":
            state = tutor._get_or_create_state(args.user_id)
            print(state.recent_history(limit=10) or "(empty)")
            continue

        try:
            run_one_turn(tutor, args.user_id, message, args.show_intent)
        except Exception:
            print("[ERROR] 本轮会话失败：")
            print(traceback.format_exc())


if __name__ == "__main__":
    raise SystemExit(main())
