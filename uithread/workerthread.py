import sys
import os
import importlib

# Ensure "uithread" can be resolved as a package
base_dir = os.path.abspath(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)


def worker_main(worker_id, input_queue, output_queue, worker_class_path):
    # Expect full path like "uithread.worker_types.EchoWorker"
    module_name, class_name = worker_class_path.rsplit('.', 1)
    mod = importlib.import_module(module_name)
    worker_cls = getattr(mod, class_name)
    worker_instance = worker_cls(worker_id)

    while True:
        msg = input_queue.get()
        if msg == "STOP":
            output_queue.put((worker_id, "Stopped"))
            break
        result = worker_instance.handle(msg)
        output_queue.put((worker_id, result))