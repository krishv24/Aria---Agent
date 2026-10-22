"""FastAPI application entry point, routing, static file mounting, and WebSocket endpoints."""

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.orders import Order, get_all_orders

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


@app.websocket("/ws/call")
async def websocket_call_endpoint(websocket: WebSocket):
    """Single WebSocket endpoint for real-time bi-directional voice call interaction."""
    await websocket.accept()
    # Logic will be implemented in subsequent stages
    await websocket.close()
