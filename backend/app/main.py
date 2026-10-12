from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base, engine
from app.models import *
from app.routes.crowd import router as crowd_router
from app.websocket.manager import manager
from app.routes.admin import router as admin_router
from app.routes.monitoring import router as monitoring_router
from app.auth import AuthenticationConfigurationError, validate_auth_configuration

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Keep table creation out of module import so configuration errors are
    # reported during application startup instead of during test discovery.
    try:
        validate_auth_configuration()
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as error:
        raise RuntimeError("PostgreSQL is unavailable.") from error
    yield


# Create FastAPI application
app = FastAPI(
    title="Smart Hospital Monitoring System",
    description="Hospital monitoring backend",
    version="1.0.0",
    lifespan=lifespan,
)


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


@app.middleware("http")
async def safe_error_middleware(request: Request, call_next):
    """Keep sanitized unexpected errors CORS-compatible for browser clients."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        response = await call_next(request)
    except Exception as error:
        logger.exception(
            "Unhandled request failure",
            extra={"request_id": request_id, "path": request.url.path, "method": request.method},
            exc_info=(type(error), error, error.__traceback__),
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    origin = request.headers.get("origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


# Crowd monitoring routes
app.include_router(crowd_router)
app.include_router(admin_router)
app.include_router(monitoring_router)


@app.exception_handler(AuthenticationConfigurationError)
async def authentication_configuration_handler(_request: Request, _error: AuthenticationConfigurationError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Authentication is not configured. Set ADMIN_TOKEN_SECRET and restart the backend."},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(_request: Request, _error: SQLAlchemyError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Database service is temporarily unavailable."},
    )


# Root endpoint
@app.get("/")
def root():

    return {
        "message": "Smart Hospital Monitoring System API",
        "status": "running"
    }


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket
):

    await manager.connect(websocket)

    try:

        while True:

            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
