import sys
import os
import importlib

# Ensure "uithread" can be resolved as a package
base_dir = os.path.abspath(os.path.dirname(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)


def worker_main(worker_id, input_queue, output_queue, worker_class_path):
    # Expect full path like "uithread.worker_types.GamepadWorker"
    module_name, class_name = worker_class_path.rsplit('.', 1)
    mod = importlib.import_module(module_name)
    worker_cls = getattr(mod, class_name)

    # Pass queues and worker_id to worker constructor
    worker_instance = worker_cls(input_queue, output_queue, worker_id)

    # Start worker run loop (blocking)
    try:
        worker_instance.run()
    except Exception as e:
        output_queue.put((worker_id, f"Exception in worker: {e}"))