import threading
from queue import Queue
from .workerthread import worker_main
import ctypes

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
    
    def get_output_queue(self):
        return self.output_queue
        
    def stop_worker(self, worker_id):
        self.send_to_worker(worker_id, "STOP")

    def shutdown(self):
        for wid in list(self.threads):
            self.stop_worker(wid)
        for thread in list(self.threads.values()):
            if thread.is_alive():
                print(f"Warning: Thread {thread.name} still alive, skipping join.")
            else:
                thread.join()

    def _async_raise(self, tid, exctype):
        """Raise an exception in the thread with id tid"""
        if not isinstance(exctype, type):
            raise TypeError("Only types can be raised")
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(tid),
            ctypes.py_object(exctype)
        )
        if res == 0:
            raise ValueError("Invalid thread ID")
        elif res > 1:
            # Revert effect if multiple threads affected
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
            raise SystemError("PyThreadState_SetAsyncExc failed")

    def force_kill_thread(self, thread):
        if not thread.is_alive():
            print("Thread is not alive.")
            return
        self._async_raise(thread.ident, SystemExit)

    def forcedKill(self, worker_id):
        print(self.threads)
        print("killing thread", worker_id)
        thread = self.threads.get(worker_id)
        if thread:
            self.force_kill_thread(thread)
            del self.threads[worker_id]  # <- Important!
            del self.input_queues[worker_id]  # Optional: cleanup input queue
            print(f"Thread {worker_id} forcibly terminated and removed.")
        else:
            print(f"No thread found for worker_id: {worker_id}")
