from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base, engine
from app.models import *
from app.routes.crowd import router as crowd_router
from app.websocket.manager import manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Keep table creation out of module import so configuration errors are
    # reported during application startup instead of during test discovery.
    try:
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


# Crowd monitoring routes
app.include_router(crowd_router)


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
