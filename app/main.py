"""FastAPI application entry point, routing, static file mounting, and WebSocket endpoints."""

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.orders import Order, get_all_orders
from app.llm import get_llm_reply

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


@app.websocket("/ws/call")
async def websocket_call_endpoint(websocket: WebSocket):
    """Single WebSocket endpoint for real-time bi-directional voice call interaction."""
    await websocket.accept()
    # Logic will be implemented in the next stage
    await websocket.close()
