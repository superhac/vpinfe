# worker_interface.py
class BaseWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id

    def handle(self, message):
        """Override in subclass"""
        raise NotImplementedError("Must implement handle()")
