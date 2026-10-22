"""FastAPI application entry point, routing, static file mounting, and WebSocket endpoints."""

from fastapi import FastAPI, WebSocket, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.orders import Order, get_all_orders
from app.llm import get_llm_reply
from app.tts import synthesize_sentence_bytes

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


@app.websocket("/ws/call")
async def websocket_call_endpoint(websocket: WebSocket):
    """Single WebSocket endpoint for real-time bi-directional voice call interaction."""
    await websocket.accept()
    # Logic will be implemented in the next stage
    await websocket.close()
