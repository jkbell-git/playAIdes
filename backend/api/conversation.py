"""REST adapter for the conversation turn (slice 2). Drains the same
ConversationService.run_turn generator the WS path streams, returning the
assembled reply (the stream:false path). Mirrors backend/api/integrations.py:
a self-contained APIRouter behind require_api_key, mounted by the app."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.api.deps import require_api_key

router = APIRouter(
    prefix="/api/v1",
    tags=["conversation"],
    dependencies=[Depends(require_api_key)],
)


class MessageIn(BaseModel):
    text: str


class MessageOut(BaseModel):
    reply: str


@router.post("/personas/{persona_id}/messages", response_model=MessageOut)
def post_message(persona_id: str, body: MessageIn, request: Request) -> MessageOut:
    # Sync handler: FastAPI runs it in its threadpool, so a slow LLM turn occupies
    # a worker but does not block the event loop. Explicit thread/streaming handling
    # for turns is a documented slice-2 open item.
    conv = getattr(request.app.state, "conversation_service", None)
    if conv is None:
        raise HTTPException(status_code=503, detail="conversation service unavailable")
    reply = ""
    for ev in conv.run_turn(persona_id, body.text):
        if ev.type == "reply_done":
            reply = ev.payload.get("text", "")
    return MessageOut(reply=reply)
