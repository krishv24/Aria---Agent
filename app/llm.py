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

# Assignment specifies llama-3.3-70b-versatile; use env var to override when the
# key's tier doesn't have that model yet (e.g. early free-tier Groq keys).
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Maximum tool-call iterations per turn to prevent infinite loops
MAX_TOOL_ITERATIONS = 5


def build_initial_messages(history: list[dict]) -> list[dict]:
    """Prepend the system prompt to the conversation history."""
    return [{"role": "system", "content": SYSTEM_PROMPT}] + history


async def run_tool_call(tool_name: str, tool_args: dict) -> str:
    """Execute the named tool function and return its result as a JSON string.

    Groq expects tool results as strings in the messages list.
    """
    func = TOOL_FUNCTIONS.get(tool_name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    result = func(**tool_args)
    return json.dumps(result, ensure_ascii=False)


async def get_llm_reply(history: list[dict]) -> AsyncGenerator[str, None]:
    """Run the full Groq tool-calling loop and stream the final text reply.

    Flow:
      1. Send conversation to Groq with tool schemas attached.
      2. If the model wants a tool call, run it and send the result back.
      3. Repeat until the model returns a plain text message (no more tool calls).
      4. Stream that final message chunk by chunk.
    """
    messages = build_initial_messages(history)

    # Tool loop: keep going until the model stops requesting tools
    for _ in range(MAX_TOOL_ITERATIONS):
        response = await _groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            # No streaming here because we need to inspect tool_calls first
            stream=False,
            temperature=0.4,  # Low temperature keeps replies factual and consistent
            max_tokens=300,   # Replies should be short (they'll be spoken)
        )

        message = response.choices[0].message

        # If no tool calls, the model is ready to reply — exit the loop
        if not message.tool_calls:
            break

        # Append the assistant's tool-call request to the conversation
        messages.append(message.model_dump(exclude_none=True))

        # Execute every requested tool and append each result
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            tool_result = await run_tool_call(tool_name, tool_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })
    else:
        # Safety: if we hit MAX_TOOL_ITERATIONS without a text reply, bail out
        yield "I'm sorry, I ran into an issue processing your request. Could you please try again?"
        return

    # Now stream the final text reply so the WebSocket can forward chunks in real-time
    final_content = message.content or ""
    if not final_content.strip():
        yield "I'm sorry, I didn't quite catch that. Could you please repeat?"
        return

    # Simulate streaming by yielding the full content as one chunk.
    # In Stage 4 (WebSocket) we'll replace this with a real streaming call.
    yield final_content
