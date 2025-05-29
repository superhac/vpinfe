# File: uithread/worker_types/gamepad_worker.py
#from inputs import get_gamepad, devices
from thirdparty.inputs import get_gamepad, devices
import time
from uithread.workerinterface import BaseWorker

class GamepadWorker(BaseWorker):
    def __init__(self, input_queue, output_queue, worker_id):
        super().__init__(input_queue, output_queue, worker_id)
        self.running = True

    def run(self):
        while self.running:
            try:
                events = devices.gamepads[0]._do_iter()
                if events is not None:
                #events = get_gamepad()  # blocks until events are available
                    for event in events:
                        # Package event info to a dict or custom class
                        event_data = {
                            'code': event.code,
                            'state': event.state,
                            'timestamp': event.timestamp,
                            # optionally, add worker id or type info here
                        }
                        self.output_queue.put([self.worker_id, event_data])
            except Exception as e:
                # Optionally handle exceptions or send error message back
                self.output_queue.put({'error': str(e)})

            # Optionally check in_queue for control commands (e.g., stop)
            while not self.input_queue.empty():
                cmd = self.input_queue.get_nowait()
                if cmd == "STOP":
                    self.running = False
                    break
            time.sleep(0.01)  # Small delay to prevent busy loop if no input