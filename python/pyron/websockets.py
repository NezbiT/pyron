"""Small WebSocket wrapper over Starlette."""

from __future__ import annotations

from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect


class PyronWebSocket:
    """What a `@app.websocket` handler iterates and sends on."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._accepted = False

    @property
    def raw(self) -> WebSocket:
        return self._ws

    async def accept(self) -> None:
        if not self._accepted:
            await self._ws.accept()
            self._accepted = True

    async def send(self, message: str | bytes | dict[str, Any]) -> None:
        await self.accept()
        if isinstance(message, dict):
            await self._ws.send_json(message)
        elif isinstance(message, bytes):
            await self._ws.send_bytes(message)
        else:
            await self._ws.send_text(str(message))

    async def receive(self) -> str | bytes | None:
        await self.accept()
        try:
            message = await self._ws.receive()
        except WebSocketDisconnect:
            return None
        if message["type"] == "websocket.disconnect":
            return None
        if message.get("text") is not None:
            return message["text"]
        return message.get("bytes")

    def __aiter__(self) -> PyronWebSocket:
        return self

    async def __anext__(self) -> str | bytes:
        item = await self.receive()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self, code: int = 1000) -> None:
        await self._ws.close(code)
