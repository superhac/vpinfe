class BaseWorker:
    def __init__(self, input_queue, output_queue, worker_id):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.worker_id = worker_id