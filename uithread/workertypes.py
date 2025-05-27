from .workerinterface import BaseWorker

class EchoWorker(BaseWorker):
    def handle(self, message):
        return f"[Echo {self.worker_id}] {message}"

class ReverseWorker(BaseWorker):
    def handle(self, message):
        return f"[Reverse {self.worker_id}] {message[::-1]}"

