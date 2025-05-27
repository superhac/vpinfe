# worker_thread.py
import threading
import time

def worker_main(worker_id, input_queue, output_queue, worker_class_path):
    # Dynamically import the worker class
    module_name, class_name = worker_class_path.rsplit('.', 1)
    mod = __import__(module_name, fromlist=[class_name])
    worker_cls = getattr(mod, class_name)
    worker_instance = worker_cls(worker_id)

    while True:
        msg = input_queue.get()
        if msg == "STOP":
            output_queue.put((worker_id, "Stopped"))
            break
        result = worker_instance.handle(msg)
        output_queue.put((worker_id, result))
