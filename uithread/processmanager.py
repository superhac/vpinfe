# uithread/process_manager.py
import threading
from queue import Queue
from .workerthread import worker_main

class ProcessManager:
    def __init__(self):
        self.input_queues = {}
        self.output_queue = Queue()
        self.threads = {}

    def start_worker(self, worker_id, worker_class_path):
        input_queue = Queue()
        thread = threading.Thread(target=worker_main, args=(
            worker_id, input_queue, self.output_queue, worker_class_path
        ))
        thread.start()
        self.input_queues[worker_id] = input_queue
        self.threads[worker_id] = thread

    def send_to_worker(self, worker_id, message):
        if worker_id in self.input_queues:
            self.input_queues[worker_id].put(message)

    def get_responses(self):
        responses = []
        while not self.output_queue.empty():
            responses.append(self.output_queue.get())
        return responses

    def stop_worker(self, worker_id):
        self.send_to_worker(worker_id, "STOP")

    def shutdown(self):
        for wid in list(self.threads):
            self.stop_worker(wid)
        for thread in self.threads.values():
            thread.join()

