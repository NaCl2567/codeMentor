from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _load_env_file(env_path: Path) -> None:
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


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace") # type: ignore
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace") # type: ignore
except Exception:
    pass


ROOT = Path(__file__).resolve().parents[1]
_load_env_file(ROOT / "backend" / ".env")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.src.agent import CodeTutorAgent  # noqa: E402
from backend.src.config import TutorConfig  # noqa: E402


class ChatRequest(BaseModel):
    user_id: str
    message: str


app = FastAPI(title="CodeTutorAgent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


cfg = TutorConfig.from_env()
if "ENABLE_NOTES" not in os.environ:
    cfg.enable_notes = False
tutor = CodeTutorAgent(cfg)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    try:
        state = tutor._get_or_create_state(req.user_id)
        intent, params = tutor._classify_intent(state, req.message)
        full_response = tutor.chat_with_intent(req.user_id, req.message, intent, params)

        payload: dict[str, Any] = {
            "response": full_response,
            "intent": intent,
            "params": params,
            "exercise_markdown": "",
            "review_markdown": "",
            "path_markdown": "",
        }

        if intent == "request_exercise":
            payload["exercise_markdown"] = full_response
            payload["response"] = "已为你生成一道练习题，请查看右侧看板。"
        elif intent == "submit_code":
            payload["review_markdown"] = full_response
            payload["response"] = "代码审查完成，请查看右侧看板。"
        elif intent == "learning_path":
            payload["path_markdown"] = full_response
            payload["response"] = "学习路径已规划完成，请查看右侧看板。"

        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc
