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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for backend agent project.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run a live LLM call (requires reachable provider and valid API key).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "backend" / "src"
    env_file = repo_root / "backend" / ".env"

    print(f"[INFO] repo_root: {repo_root}")
    print(f"[INFO] src_dir:   {src_dir}")
    print(f"[INFO] env_file:  {env_file}")

    load_env_file(env_file)
    sys.path.insert(0, str(src_dir))

    try:
        import compileall

        ok = compileall.compile_dir(str(src_dir), force=True, quiet=1)
        if not ok:
            print("[FAIL] compileall failed for backend/src")
            return 1
        print("[OK] compileall passed")
    except Exception:
        print("[FAIL] compile stage crashed")
        print(traceback.format_exc())
        return 1

    try:
        from src.config import TutorConfig
        from src.agent import CodeTutorAgent
    except Exception:
        print("[FAIL] import failed")
        print(traceback.format_exc())
        return 1
    print("[OK] import config/agent passed")

    try:
        cfg = TutorConfig.from_env()
        # On Windows consoles with legacy encoding, note tool registration prints emoji
        # from dependency and may crash with UnicodeEncodeError.
        cfg.enable_notes = False
        tutor = CodeTutorAgent(cfg)
        print("[OK] CodeTutorAgent init passed")
        print(f"[INFO] provider={cfg.llm_provider}, model={cfg.llm_model_id}")
    except Exception:
        print("[FAIL] CodeTutorAgent init failed")
        print(traceback.format_exc())
        return 1

    try:
        state = tutor._get_or_create_state("smoke_test_user")
        assert state.user_id == "smoke_test_user"
        print("[OK] state creation passed")
    except Exception:
        print("[FAIL] state creation failed")
        print(traceback.format_exc())
        return 1

    if not args.live:
        print("[DONE] offline checks passed. Use --live to test one real LLM call.")
        return 0

    try:
        intent, params = tutor._classify_intent(state, "给我一题 Python 基础练习")
        print(f"[OK] live classify passed: intent={intent}, params={params}")
        return 0
    except Exception:
        print("[FAIL] live classify failed (check API key/provider/network)")
        print(traceback.format_exc())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
