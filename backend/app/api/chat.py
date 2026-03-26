"""
chat.py

Chat endpoint with conversation memory.

WHY CONVERSATION MEMORY:
Without memory, every question is isolated. The user cannot ask
follow-up questions like "which of those have been paid?" after
asking about billing documents. We store the last N exchanges
in a simple in-memory list and include them as context.

WHY IN-MEMORY (not a database):
For a demo submission, in-memory is sufficient and zero-infra.
The conversation resets when the server restarts — acceptable for now.
"""

import logging
from collections import deque
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.llm.pipeline import run_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])

# ── Conversation memory ───────────────────────────────────────────────────────
# Stores the last 10 exchanges per session.
# Key: session_id (string), Value: deque of message dicts
# deque with maxlen automatically drops oldest messages.

MAX_HISTORY = 10
_conversations: dict[str, deque] = {}


def _get_history(session_id: str) -> list[dict]:
    """Returns conversation history for a session as a plain list."""
    if session_id not in _conversations:
        _conversations[session_id] = deque(maxlen=MAX_HISTORY)
    return list(_conversations[session_id])


def _add_to_history(session_id: str, role: str, content: str) -> None:
    """Appends a message to the session's conversation history."""
    if session_id not in _conversations:
        _conversations[session_id] = deque(maxlen=MAX_HISTORY)
    _conversations[session_id].append({"role": role, "content": content})


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    session_id: str = "default"    # frontend passes a UUID per browser tab


class ChatResponse(BaseModel):
    answer:             str
    cypher:             str | None
    rows:               list[dict]
    highlighted_nodes:  list[str]
    is_domain:          bool
    session_id:         str
    history:            list[dict]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Accepts a question and returns a data-backed answer.

    The session_id ties the conversation to a browser tab.
    The frontend generates a UUID on load and sends it with every request.
    """
    question   = request.question.strip()
    session_id = request.session_id

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    logger.info(f"[{session_id}] Question: {question}")

    # Store user message in history
    _add_to_history(session_id, "user", question)

    # Run the full pipeline
    result = run_query(question)

    # Store assistant answer in history
    _add_to_history(session_id, "assistant", result["answer"])

    logger.info(f"[{session_id}] Answer: {result['answer'][:80]}...")

    return ChatResponse(
        answer            = result["answer"],
        cypher            = result.get("cypher"),
        rows              = result.get("rows", []),
        highlighted_nodes = result.get("highlighted_nodes", []),
        is_domain         = result["is_domain"],
        session_id        = session_id,
        history           = _get_history(session_id),
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """Returns the full conversation history for a session."""
    return {
        "session_id": session_id,
        "history":    _get_history(session_id),
    }


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """Clears conversation history for a session."""
    if session_id in _conversations:
        _conversations[session_id].clear()
    return {"session_id": session_id, "cleared": True}