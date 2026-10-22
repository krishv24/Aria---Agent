"""Post-call structured summary generation in JSON format."""

import asyncio
from enum import Enum
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from groq import AsyncGroq
from pydantic import BaseModel, Field, field_validator

load_dotenv()

logger = logging.getLogger("aria.summary")

# Shared Groq client for post-call analytics
_groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class CustomerIntent(str, Enum):
    """Enumeration of recognized customer query intents."""
    ORDER_TRACKING = "ORDER_TRACKING"
    CANCELLATION = "CANCELLATION"
    RETURN_REFUND = "RETURN_REFUND"
    POLICY_QUESTION = "POLICY_QUESTION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    OTHER = "OTHER"


class ResolutionStatus(str, Enum):
    """Outcome classification of the customer support interaction."""
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    ESCALATION_NEEDED = "ESCALATION_NEEDED"


class CallSummary(BaseModel):
    """Structured post-call outcome report."""
    customer_intent: CustomerIntent
    order_id: str | None = None
    resolution_status: ResolutionStatus
    call_summary: str = Field(description="1-3 sentence summary of query and outcome")

    @field_validator("customer_intent", mode="before")
    @classmethod
    def normalize_intent(cls, v: Any) -> str:
        """Normalize casing and spacing for resilient enum matching."""
        if isinstance(v, str):
            clean = v.strip().upper().replace(" ", "_")
            if clean in CustomerIntent.__members__:
                return clean
        return CustomerIntent.OTHER.value

    @field_validator("resolution_status", mode="before")
    @classmethod
    def normalize_resolution(cls, v: Any) -> str:
        """Normalize casing and spacing for resilient resolution matching."""
        if isinstance(v, str):
            clean = v.strip().upper().replace(" ", "_")
            if clean in ResolutionStatus.__members__:
                return clean
        return ResolutionStatus.UNRESOLVED.value

    @field_validator("order_id", mode="before")
    @classmethod
    def normalize_order_id(cls, v: Any) -> str | None:
        """Clean string representations of null or empty order IDs."""
        if v is None:
            return None
        if isinstance(v, str):
            clean = v.strip()
            if not clean or clean.lower() in {"none", "null", "n/a", "unknown"}:
                return None
            return clean.upper()
        return None


SUMMARY_SYSTEM_PROMPT = """You are a quality assurance auditor for Aura Skincare customer support calls.
Analyze the provided transcript and produce a JSON object with this exact structure:
{
  "customer_intent": "ORDER_TRACKING" | "CANCELLATION" | "RETURN_REFUND" | "POLICY_QUESTION" | "OUT_OF_SCOPE" | "OTHER",
  "order_id": "ORD-XXX" or null,
  "resolution_status": "RESOLVED" | "UNRESOLVED" | "ESCALATION_NEEDED",
  "call_summary": "1 to 2 concise sentences describing what the customer asked and the final resolution."
}

Rules:
- customer_intent must be exactly one of: ORDER_TRACKING, CANCELLATION, RETURN_REFUND, POLICY_QUESTION, OUT_OF_SCOPE, OTHER.
- resolution_status must be exactly one of: RESOLVED, UNRESOLVED, ESCALATION_NEEDED.
- If an order was referenced (e.g. ORD-101), extract it into order_id; otherwise set order_id to null.
- Output ONLY valid JSON matching the schema."""


def format_transcript(history: list[dict]) -> str:
    """Format conversation history into a clean human-readable dialogue."""
    lines: list[str] = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"Customer: {content}")
        elif role == "assistant":
            lines.append(f"Aria: {content}")
    return "\n".join(lines)


def has_substantive_conversation(history: list[dict]) -> bool:
    """Determine whether the call contained meaningful customer speech."""
    return any(
        msg.get("role") == "user" and len(msg.get("content", "").strip()) > 0
        for msg in history
    )


def make_fallback_summary(reason: str = "No customer conversation took place.") -> CallSummary:
    """Safe fallback summary when calls are empty or LLM extraction fails."""
    return CallSummary(
        customer_intent=CustomerIntent.OTHER,
        order_id=None,
        resolution_status=ResolutionStatus.UNRESOLVED,
        call_summary=reason,
    )


async def _request_groq_summary(transcript: str) -> CallSummary:
    """Send transcript to Groq in JSON mode and parse the resulting Pydantic model."""
    response = await _groq_client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"TRANSCRIPT:\n{transcript}"},
        ],
        response_format={"type": "json_object"},
        max_tokens=250,
    )
    raw_content = response.choices[0].message.content or "{}"
    data = json.loads(raw_content)
    return CallSummary.model_validate(data)


async def generate_call_summary(history: list[dict]) -> CallSummary:
    """Generate structured post-call summary with automatic retry and graceful fallback.

    1. Checks if customer conversation occurred (handles empty calls gracefully).
    2. Calls Groq with JSON mode.
    3. Retries once if validation fails.
    4. Returns safe fallback object if all attempts fail.
    """
    if not has_substantive_conversation(history):
        return make_fallback_summary("Call ended before customer conversation took place.")

    transcript = format_transcript(history)

    # Retry once if parsing or network fails
    for attempt in range(2):
        try:
            return await _request_groq_summary(transcript)
        except Exception as exc:
            logger.warning("[Summary] Attempt %s failed: %s", attempt + 1, exc)
            if attempt == 0:
                await asyncio.sleep(0.5)

    return make_fallback_summary("Call completed. Detailed summary could not be extracted.")
