import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.orders import Order, get_all_orders
from app.llm import get_llm_reply
from app.tts import synthesize_sentence_bytes, stream_sentences
from app.summary import CallSummary, generate_call_summary

logger = logging.getLogger("aria.main")

# Initialize FastAPI application instance
app = FastAPI(title="Aura Skincare - Aria Voice Support Agent")

# Mount static directory for frontend assets (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_index():
    """Serve the single-page voice customer support interface."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint to verify server status."""
    return {"status": "ok"}


@app.get("/api/orders", response_model=list[Order])
async def list_orders():
    """Return all mock orders for the frontend test helper card."""
    return get_all_orders()


class ChatRequest(BaseModel):
    """Request body for the temporary text-based chat test endpoint."""
    history: list[dict]  # List of {"role": "user"|"assistant", "content": "..."}


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Temporary text chat endpoint for testing the LLM + tool loop before adding voice.

    Accepts a conversation history and streams back the assistant's reply.
    This endpoint will be removed once the WebSocket voice pipeline is complete.
    """
    async def generate():
        async for chunk in get_llm_reply(request.history):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


class TTSRequest(BaseModel):
    """Request model for text-to-speech synthesis."""
    text: str
    simulate_failure: bool = False


@app.post("/api/tts")
async def tts_endpoint(request: TTSRequest):
    """Synthesize speech audio for a single sentence using edge-tts.

    Returns MP3 audio bytes if successful.
    If simulate_failure is True or edge-tts fails, raises HTTP 500 so
    the frontend can trigger its window.speechSynthesis fallback.
    """
    if request.simulate_failure:
        raise HTTPException(
            status_code=500,
            detail="Simulated Edge-TTS failure to test browser fallback",
        )

    try:
        audio_bytes = await synthesize_sentence_bytes(request.text)
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="No audio generated")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class SummaryRequest(BaseModel):
    """Request model for generating a post-call summary from conversation history."""
    history: list[dict]


@app.post("/api/summary", response_model=CallSummary)
async def summary_endpoint(request: SummaryRequest):
    """Generate structured JSON post-call summary for a conversation history."""
    return await generate_call_summary(request.history)


@app.websocket("/ws/call")
async def websocket_call_endpoint(websocket: WebSocket):
    """Single WebSocket endpoint orchestrating the real-time voice call session.

    Protocol:
    - Client -> Server:
        {"type": "user_text", "text": "..."}
        {"type": "interrupt"}
        {"type": "end_call"}
    - Server -> Client:
        {"type": "state", "value": "listening"|"thinking"|"speaking"|"idle"}
        {"type": "agent_text", "text": "...", "is_new_turn": bool}
        {"type": "audio"} (immediately followed by binary audio bytes)
        {"type": "fallback_speak", "text": "..."}
        {"type": "error", "message": "..."}
    """
    await websocket.accept()

    # 1. Per-call conversation history kept in memory for this connection
    history: list[dict] = []

    # Reference to the active agent generation task (cancellable during barge-in)
    current_agent_task: asyncio.Task | None = None

    def cancel_active_task():
        """Cancel any running LLM or TTS task when the user interrupts or disconnects."""
        nonlocal current_agent_task
        if current_agent_task and not current_agent_task.done():
            current_agent_task.cancel()
        current_agent_task = None

    async def speak_sentence_to_client(sentence: str, is_new_turn: bool = False):
        """Send sentence text to transcript and stream synthesized audio bytes to the browser."""
        # 1. Display text in live transcript
        await websocket.send_json({
            "type": "agent_text",
            "text": sentence,
            "is_new_turn": is_new_turn,
        })

        # 2. Update state badge to speaking
        await websocket.send_json({"type": "state", "value": "speaking"})

        # 3. Synthesize sentence audio via Edge-TTS
        try:
            audio_bytes = await synthesize_sentence_bytes(sentence)
            if audio_bytes:
                # Notify client that raw audio bytes will follow in the next binary frame
                await websocket.send_json({"type": "audio"})
                await websocket.send_bytes(audio_bytes)
            else:
                # Edge-TTS produced no audio; instruct client to use browser speech synthesis
                await websocket.send_json({"type": "fallback_speak", "text": sentence})
        except Exception as tts_err:
            logger.warning("[TTS Error] %s, falling back to client speech synthesis", tts_err)
            await websocket.send_json({"type": "fallback_speak", "text": sentence})

    async def run_agent_turn(user_utterance: str):
        """Execute tool-calling LLM, split streaming tokens into sentences, and send to TTS."""
        history.append({"role": "user", "content": user_utterance})
        await websocket.send_json({"type": "state", "value": "thinking"})

        full_reply_parts: list[str] = []
        is_first_sentence = True

        try:
            # LLM generates tokens; tool-loop is resolved automatically inside get_llm_reply
            token_stream = get_llm_reply(history)

            # Split incoming token stream into sentences as soon as punctuation arrives
            async for sentence in stream_sentences(token_stream):
                clean_sentence = sentence.strip()
                if not clean_sentence:
                    continue

                full_reply_parts.append(clean_sentence)
                await speak_sentence_to_client(clean_sentence, is_new_turn=is_first_sentence)
                is_first_sentence = False

            # Add the completed assistant reply to history for subsequent conversational turns
            full_reply = " ".join(full_reply_parts)
            if full_reply:
                history.append({"role": "assistant", "content": full_reply})

        except asyncio.CancelledError:
            logger.info("[Agent Task] Interrupted by user barge-in")
            # Preserve partial spoken reply so the agent maintains conversation context
            if full_reply_parts:
                history.append({"role": "assistant", "content": " ".join(full_reply_parts)})
            raise
        except Exception as exc:
            logger.exception("[Agent Task Error] %s", exc)
            await websocket.send_json({"type": "error", "message": f"Error: {exc}"})
            await websocket.send_json({"type": "state", "value": "listening"})

    try:
        # 4. Aria greets first when the call starts
        INITIAL_GREETING = "Hello! Welcome to Aura Skincare. I'm Aria, your customer support assistant. How can I help you today?"
        history.append({"role": "assistant", "content": INITIAL_GREETING})
        await speak_sentence_to_client(INITIAL_GREETING, is_new_turn=True)

        # Main message loop listening for browser events
        while True:
            raw_message = await websocket.receive_text()
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "user_text":
                text = data.get("text", "").strip()
                # 3. Ignore empty or 1-character transcripts (e.g. noise pops or single letters)
                if len(text) <= 1:
                    continue

                # Interrupt any prior turn still processing before starting the new turn
                cancel_active_task()
                current_agent_task = asyncio.create_task(run_agent_turn(text))

            elif msg_type == "interrupt":
                # 2. User barged in (spoke 2+ words while agent was speaking/thinking)
                logger.info("[WebSocket] Barge-in interrupt received: cancelling active agent task")
                cancel_active_task()
                await websocket.send_json({"type": "state", "value": "listening"})

            elif msg_type == "end_call":
                # 5. User ended the call
                logger.info("[WebSocket] User ended call: generating post-call summary")
                cancel_active_task()

                # Generate structured JSON summary from full in-memory conversation history
                summary = await generate_call_summary(history)
                await websocket.send_json({
                    "type": "summary",
                    "data": summary.model_dump(),
                    "transcript": history,
                })

                await websocket.send_json({"type": "state", "value": "idle"})
                break

    except WebSocketDisconnect:
        logger.info("[WebSocket] Client disconnected")
    finally:
        # 5. Clean up pending tasks on connection close
        cancel_active_task()
