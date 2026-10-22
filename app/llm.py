import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from groq import AsyncGroq, RateLimitError, APIStatusError

from app.prompts import SYSTEM_PROMPT
from app.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

load_dotenv()

logger = logging.getLogger("aria.llm")


def get_groq_api_key() -> str:
    """Retrieve and clean the Groq API key from environment variables."""
    return os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")


def get_groq_client() -> AsyncGroq:
    """Instantiate AsyncGroq with sanitized API key."""
    key = get_groq_api_key()
    if not key:
        logger.error("[Groq] GROQ_API_KEY environment variable is missing or empty! Please set it in your environment settings.")
    return AsyncGroq(api_key=key or "missing_key")


# Maximum tool-call iterations per turn to prevent runaway loops
MAX_TOOL_ITERATIONS = 5


def build_messages(history: list[dict]) -> list[dict]:
    """Prepend the system prompt to the conversation history."""
    return [{"role": "system", "content": SYSTEM_PROMPT}] + history


async def run_tool_call(tool_name: str, tool_args: dict) -> str:
    """Execute the named tool and return its result as a JSON string.

    Groq expects tool results as plain strings in the messages list.
    """
    func = TOOL_FUNCTIONS.get(tool_name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = func(**tool_args)
    return json.dumps(result, ensure_ascii=False)


def _make_api_params(messages: list[dict], stream: bool) -> dict:
    """Build the keyword arguments for a Groq chat completion call."""
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    reasoning_effort = "low" if "gpt-oss" in model else None

    params: dict = {
        "model": model,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "stream": stream,
        "max_tokens": 300,  # Short — replies are spoken aloud
    }
    if reasoning_effort:
        params["reasoning_effort"] = reasoning_effort
    return params


def strip_reasoning(content: str) -> str:
    """Remove any leaked <think>...</think> or similar reasoning wrappers."""
    import re
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return content.strip()


async def _call_groq_with_retry(messages: list[dict], stream: bool):
    """Invoke Groq completions with 1 automatic retry on rate limit (429) errors."""
    client = get_groq_client()
    params = _make_api_params(messages, stream=stream)
    for attempt in range(2):
        try:
            return await client.chat.completions.create(**params)
        except (RateLimitError, APIStatusError) as exc:
            is_429 = isinstance(exc, RateLimitError) or getattr(exc, "status_code", None) == 429
            if is_429 and attempt == 0:
                logger.warning("[Groq] Rate limit (429) encountered. Retrying in 1.0s...")
                await asyncio.sleep(1.0)
                continue
            logger.error("[Groq Call Failure] Status %s: %s", getattr(exc, "status_code", "unknown"), exc)
            raise


async def get_llm_reply(history: list[dict]) -> AsyncGenerator[str, None]:
    """Run the Groq tool-calling loop then stream back only the visible reply."""
    messages = build_messages(history)

    try:
        # --- Tool-calling loop (non-streaming so we can see tool_calls) ---
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await _call_groq_with_retry(messages, stream=False)
            message = response.choices[0].message

            # No tool calls means the model is ready to give a final reply
            if not message.tool_calls:
                break

            # Add the assistant's tool-call message to conversation history
            messages.append(message.model_dump(exclude_unset=True, exclude_none=True))

            # Execute every requested tool and record results
            for tool_call in message.tool_calls:
                tool_result = await run_tool_call(
                    tool_call.function.name,
                    json.loads(tool_call.function.arguments),
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
        else:
            # Hit iteration limit without a text reply — give a safe fallback
            yield "I'm sorry, I ran into an issue looking that up. Could you please try again?"
            return

        # --- Final streaming reply — only yield content, drop reasoning chunks ---
        stream = await _call_groq_with_retry(messages, stream=True)

        full_reply = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta

            # delta.reasoning is internal thinking — never send to TTS
            if not delta.content:
                continue

            full_reply += delta.content
            yield delta.content

        # If streaming produced nothing, give a safe fallback
        if not full_reply.strip():
            yield "I'm sorry, I didn't catch that. Could you please repeat?"
            return

    except (RateLimitError, APIStatusError) as exc:
        status_code = getattr(exc, "status_code", None)
        logger.error("[Groq API Exception] status_code=%s, error=%s", status_code, exc)
        is_429 = isinstance(exc, RateLimitError) or status_code == 429
        if is_429:
            yield "Please give me just a moment to catch up, and try asking again."
        elif status_code == 401:
            logger.error("[Groq Auth Failure] 401 Unauthorized: GROQ_API_KEY is missing or invalid on server.")
            yield "I am having trouble connecting right now. Please check the API configuration."
        else:
            yield "I am having trouble connecting right now. Please try again in a moment."
    except Exception as exc:
        logger.exception("[Groq Turn Error] %s", exc)
        yield "I ran into a temporary issue. Could you please repeat that?"
