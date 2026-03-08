from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)


manager = ConnectionManager()


@router.websocket("/ws/agent/{agent_name}")
async def agent_websocket(websocket: WebSocket, agent_name: str):
    session_id = websocket.query_params.get("session_id", "default")
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            query = message.get("query", "")

            await manager.send_message({
                "type": "status",
                "status": "processing",
                "agent": agent_name,
            }, websocket)

            # Placeholder response — will be wired to runtime
            await manager.send_message({
                "type": "response",
                "agent": agent_name,
                "answer": f"[WebSocket] Received: {query}",
                "session_id": session_id,
            }, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
