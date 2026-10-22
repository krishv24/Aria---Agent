"""Groq LLM client, conversation management, and tool-calling loop."""

import json
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from groq import AsyncGroq

from app.prompts import SYSTEM_PROMPT
from app.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

load_dotenv()

# One shared async client for all calls in this process
_groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))

# Assignment specifies llama-3.3-70b-versatile; override via GROQ_MODEL env var
# when the key tier only has different models available.
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Maximum tool-call iterations per turn to prevent runaway loops
MAX_TOOL_ITERATIONS = 5

# Only apply reasoning_effort for models that support it (the gpt-oss family).
# Llama models don't accept this param and will error if we pass it.
REASONING_EFFORT = "low" if "gpt-oss" in MODEL else None


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
    """Build the keyword arguments for a Groq chat completion call.

    Kept in one place so the tool loop and streaming call stay in sync.
    """
    params: dict = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "stream": stream,
        "max_tokens": 300,  # Short — replies are spoken aloud
    }
    # reasoning_effort is only valid for gpt-oss models; skip for Llama
    if REASONING_EFFORT:
        params["reasoning_effort"] = REASONING_EFFORT
    return params


def strip_reasoning(content: str) -> str:
    """Remove any leaked <think>...</think> or similar reasoning wrappers.

    Some models embed chain-of-thought inside content even when reasoning_effort
    is set. We never want that text reaching TTS or the transcript.
    """
    import re
    # Strip common reasoning wrapper tags just in case
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return content.strip()


async def get_llm_reply(history: list[dict]) -> AsyncGenerator[str, None]:
    """Run the Groq tool-calling loop then stream back only the visible reply.

    Flow:
      1. Call Groq (non-streaming) so we can inspect tool_calls.
      2. If the model wants a tool, run it and send the result back.
      3. Repeat until no more tool calls (or MAX_TOOL_ITERATIONS hit).
      4. Make a final streaming call and yield only delta.content chunks,
         silently dropping any delta.reasoning chunks (channel='analysis').
    """
    messages = build_messages(history)

    # --- Tool-calling loop (non-streaming so we can see tool_calls) ---
    for _ in range(MAX_TOOL_ITERATIONS):
        response = await _groq_client.chat.completions.create(
            **_make_api_params(messages, stream=False)
        )

        message = response.choices[0].message

        # No tool calls means the model is ready to give a final reply
        if not message.tool_calls:
            break

        # Add the assistant's tool-call message to conversation history
        # exclude_unset avoids sending None fields the API rejects
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
        yield "I'm sorry, I ran into a problem processing that. Could you please try again?"
        return

    # --- Final streaming reply — only yield content, drop reasoning chunks ---
    # We make a fresh streaming call so the WebSocket can forward chunks in real-time.
    # The tool results are already in `messages`, so the model just needs to respond.
    stream = await _groq_client.chat.completions.create(
        **_make_api_params(messages, stream=True)
    )

    full_reply = ""
    async for chunk in stream:
        delta = chunk.choices[0].delta

        # delta.reasoning (channel='analysis') is internal thinking — never send to TTS
        # We only forward delta.content, which is the actual spoken reply
        if not delta.content:
            continue

        full_reply += delta.content
        yield delta.content

    # If streaming produced nothing, give a safe fallback
    if not full_reply.strip():
        yield "I'm sorry, I didn't catch that. Could you please repeat?"
        return

    # Sanity-check: strip any reasoning that leaked into the content field
    # (this does not affect what was already yielded — it's logged only)
    cleaned = strip_reasoning(full_reply)
    if cleaned != full_reply:
        # Log the leak so we can catch it during testing
        print(f"[LLM] Warning: reasoning text found in content and stripped.")
