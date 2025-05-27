# uithread/worker_interface.py
class BaseWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id

    def handle(self, message):
        raise NotImplementedError("Must implement handle()")