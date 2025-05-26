from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QTimer
from multiprocessing.shared_memory import SharedMemory


class ImageWorkerManager:
    def __init__(self, window, tables, command_queue, result_queue):
        self.window = window
        self.tables = tables
        self.command_queue = command_queue
        self.result_queue = result_queue
        self.current_index = 0

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_for_image)
        self.timer.start(50)

    def set_image_by_index(self, index):
        self.current_index = index
        self.command_queue.put({"action": "load", "index": index})

    def load_next(self):
        if not self.tables:
            return
        self.current_index = (self.current_index + 1) % self.tables.getTableCount()
        self.command_queue.put({"action": "load", "index": self.current_index})

    def load_previous(self):
        if not self.tables:
            return
        self.current_index = (self.current_index - 1 + self.tables.getTableCount()) % self.tables.getTableCount()
        self.command_queue.put({"action": "load", "index": self.current_index})

    def check_for_image(self):
        while not self.result_queue.empty():
            result = self.result_queue.get()
            
            if isinstance(result, dict) and "error" in result:
                # Handle the error/traceback output from the worker
                print("[Manager] Error from worker:")
                print(result["error"])
                # Optionally: show an error dialog or log it
                continue

            try:
                index, shm_name, size = result
                shm = SharedMemory(name=shm_name)
                data = bytes(shm.buf[:size])
                pixmap = QPixmap()
                pixmap.loadFromData(data, "BMP")
                self.window.set_pixmap(pixmap)
                shm.close()
                shm.unlink()
            except Exception as e:
                print(f"[Manager] Exception in check_for_image: {e}")

    def loadLogo(self):
        self.command_queue.put({"action": "load_logo"})

    def shutdown(self):
        self.command_queue.put({"action": "quit"})
        self.timer.stop()



