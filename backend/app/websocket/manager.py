import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        connections = self.active_connections.copy()

        async def send(connection):
            try:
                await asyncio.wait_for(connection.send_json(data), timeout=2)
                return connection, None
            except Exception as error:
                return connection, error

        results = await asyncio.gather(*(send(connection) for connection in connections))
        for connection, error in results:
            if error is not None:
                logger.warning("websocket broadcast failed; removing client", exc_info=(type(error), error, error.__traceback__))
                self.disconnect(connection)


manager = ConnectionManager()
