from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass


ROOT = Path(__file__).resolve().parents[1]
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
        response = tutor.chat_with_intent(req.user_id, req.message, intent, params)

        payload: dict[str, Any] = {
            "response": response,
            "intent": intent,
            "params": params,
            "exercise_markdown": "",
            "review_markdown": "",
            "path_markdown": "",
        }

        if intent == "request_exercise":
            payload["exercise_markdown"] = response
        elif intent == "submit_code":
            payload["review_markdown"] = response
        elif intent == "learning_path":
            payload["path_markdown"] = response

        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc
