from __future__ import annotations

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.deps import get_current_user_ws
from src.api.realtime import manager
from src.api.routes_alerts import router as alerts_router
from src.api.routes_auth import router as auth_router
from src.api.routes_auth import user_router
from src.api.routes_devices import router as devices_router
from src.api.routes_usage import router as usage_router
from src.api.settings import settings

openapi_tags = [
    {"name": "health", "description": "Service health and docs."},
    {"name": "auth", "description": "Registration and login endpoints (JWT)."},
    {"name": "user", "description": "User profile endpoints."},
    {"name": "devices", "description": "Device CRUD endpoints."},
    {"name": "usage", "description": "Ingestion and usage endpoints."},
    {"name": "alerts", "description": "Alert rules, evaluation outputs, and notification history."},
    {"name": "realtime", "description": "WebSocket realtime updates."},
]

app = FastAPI(
    title="Energy Usage Monitoring API",
    description=(
        "Backend API for energy usage monitoring platform: authentication, device management, "
        "readings ingestion, analytics, alerts, and realtime updates.\n\n"
        "WebSocket usage:\n"
        "- Connect to `/ws/updates?token=JWT`\n"
        "- Server will send JSON messages like:\n"
        "  - `{type: 'reading_latest', device_id, data: {...}}`\n"
        "  - `{type: 'alert_triggered', data: {...}}`\n"
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["health"], summary="Health check", operation_id="health_check")
def health_check():
    """Simple health check endpoint."""
    return {"message": "Healthy"}


@app.get(
    "/docs/websocket",
    tags=["realtime"],
    summary="WebSocket usage help",
    description="Returns information on how to connect to the realtime WebSocket.",
    operation_id="docs_websocket_help",
)
def websocket_help():
    """Explain how to connect to the realtime WebSocket and what messages look like."""
    return {
        "url": "/ws/updates?token=JWT",
        "notes": [
            "Provide JWT as query parameter token (same token as Authorization bearer).",
            "Messages are JSON. Known types: reading_latest, alert_triggered.",
        ],
    }


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(devices_router)
app.include_router(usage_router)
app.include_router(alerts_router)


@app.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket, user: dict = Depends(get_current_user_ws)):
    """
    WebSocket endpoint for realtime updates.

    Connect with:
      ws://<host>:<port>/ws/updates?token=<JWT>
    """
    user_id = user["id"]
    await manager.connect(user_id, websocket)
    try:
        # Keep connection alive by receiving messages (optional client pings).
        while True:
            _ = await websocket.receive_text()
            # Echo is not required; ignore client messages.
    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
    except Exception:
        await manager.disconnect(user_id, websocket)
        raise
