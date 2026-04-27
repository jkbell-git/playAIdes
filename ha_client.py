"""HTTP client for Home Assistant's conversation API.

Wraps POST /api/conversation/process. Returns normalized
ConversationResponse with success/error_code/speech_text shape.

Designed so playAIdes.chat() never has to interpret HA's response shape
or HTTP errors directly — it just gets a speech_text it can hand to TTS
and a success flag for branching.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class ConversationResponse:
    success: bool
    speech_text: str
    conversation_id: Optional[str]
    error_code: Optional[str]


# User-facing fallback strings. Kept here so they're easy to localize later.
_FALLBACK_NO_INTENT = "I didn't catch that — try rephrasing?"
_FALLBACK_UNREACHABLE = "I can't reach the house right now."
_FALLBACK_HTTP_ERROR = "I'm having trouble talking to the house — try again in a moment."


class HAClient:
    """Thin wrapper over HA's conversation REST endpoint."""

    def __init__(self, base_url: str, token: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def converse(
        self,
        text: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ConversationResponse:
        url = f"{self.base_url}/api/conversation/process"
        body: dict = {"text": text}
        if agent_id:
            body["agent_id"] = agent_id
        if conversation_id:
            body["conversation_id"] = conversation_id

        try:
            resp = requests.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout, ConnectionError) as e:
            logger.warning("HA conversation unreachable: %s", e)
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_UNREACHABLE,
                conversation_id=None,
                error_code="ha_unreachable",
            )

        if resp.status_code != 200:
            logger.warning("HA conversation returned %s", resp.status_code)
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_HTTP_ERROR,
                conversation_id=None,
                error_code=f"ha_http_{resp.status_code}",
            )

        try:
            payload = resp.json()
        except ValueError as e:
            logger.warning("HA conversation returned non-JSON: %s", e)
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_HTTP_ERROR,
                conversation_id=None,
                error_code="ha_bad_json",
            )

        response_obj = payload.get("response", {}) or {}
        speech = (
            response_obj.get("speech", {}).get("plain", {}).get("speech")
            or ""
        )
        conv_id = payload.get("conversation_id")
        response_type = response_obj.get("response_type")
        error_code = (response_obj.get("data") or {}).get("code")

        if response_type == "error" or error_code:
            # HA understood our HTTP request but couldn't fulfill the intent.
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_NO_INTENT,
                conversation_id=conv_id,
                error_code=error_code or "ha_response_error",
            )

        return ConversationResponse(
            success=True,
            speech_text=speech,
            conversation_id=conv_id,
            error_code=None,
        )

    def health_check(self) -> bool:
        try:
            resp = requests.get(
                f"{self.base_url}/api/",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False
