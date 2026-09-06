class EventPublisher:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0

    async def publish(self, event, payload=None, request_id=None):
        self.sequence += 1
        await self.socket.send_json({"event": event, "payload": payload or {}, "sequence": self.sequence, "request_id": request_id})
