
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.database import Base, engine
from app.models import *
from app.routes.crowd import router as crowd_router
from app.websocket.manager import manager
from fastapi.middleware.cors import CORSMiddleware

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Smart Hospital Monitoring System",
    description="Hospital monitoring backend",
    version="1.0.0"
)
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


app.include_router(crowd_router)


@app.get("/")
def root():
    return {
        "message": "Smart Hospital Monitoring System API",
        "status": "running"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await manager.connect(websocket)

    try:

        while True:

            await websocket.receive_text()

    except WebSocketDisconnect:

        manager.disconnect(websocket)