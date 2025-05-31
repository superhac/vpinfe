from multiprocessing import Process, shared_memory, Queue
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
import os
import time
import logging
import multiprocessing.resource_tracker
from screennames import ScreenNames
import traceback
from filesutils import FilesUtils
import logging

# Assets
logoImage = FilesUtils.get_asset_path("VPinFE_logo_main.png")
missingImage = FilesUtils.get_asset_path("file_missing.png")

def fix_resource_tracker():
    import multiprocessing.resource_tracker
    def noop(*args, **kwargs): pass
    multiprocessing.resource_tracker.unregister = noop
    multiprocessing.resource_tracker.register = noop



class ImageCacheWorker(Process):
    logger = None
    
    def __init__(self, tables, screenname: ScreenNames, command_queue: Queue, result_queue: Queue, screen_size):
        super().__init__()
        ImageCacheWorker.logger = logging.getLogger()
        self.tables = tables
        self.screenname = screenname
        self.command_queue = command_queue
        self.result_queue = result_queue
        self.screen_size = screen_size
        self.cache = {}
        self.shared_memory_refs = {}
        self.max_cache = 50
        self.last_cached_index = -1
        fix_resource_tracker()
       
    def run(self):
        try:
            while True:
                try:
                    msg = self.command_queue.get_nowait()
                except:
                    msg = None

                if msg:
                    logging.info(f"[{self.name}] Received message: {msg}")
                    if msg == 'quit':
                        self.cleanup()
                        return

                    if isinstance(msg, dict):
                        action = msg.get("action")
                        index = msg.get("index", -1)

                        if action == "quit":
                            self.cleanup()
                            return
                        elif action == "load" and index >= 0:
                            self.handle_request(index)
                        elif action == "load_next" and index >= 0:
                            self.load_next(index)
                        elif action == "load_previous" and index >= 0:
                            self.load_previous(index)
                        elif action == "load_logo":
                            self.load_logo_image()
                            self.preload_surrounding(0)  # Start caching around index 0

                # This will run ~100x/second regardless of queue state
                self.background_cache_step()
                time.sleep(0.01)

        except Exception:
            # Send traceback to result_queue
            tb = traceback.format_exc()
            self.result_queue.put({"error": tb})
            logging.error(f"Unhandled exception in worker:\n{tb}")

    def handle_request(self, index):
        self.load_and_send(index)
        if not self.is_index_within_cache(index):
            logging.info(f"Extending cache near index {index}")
            self.preload_surrounding(index)
        self.last_cached_index = index

    def is_index_within_cache(self, index):
        return hasattr(self, 'cache_order') and index in self.cache_order

    def getMissingImage(self, path: str) -> QPixmap:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return pixmap

        logging.warning(f"Failed to load image at {path}. Using fallback.")
        fallback_path = missingImage
        fallback_pixmap = QPixmap(fallback_path)
        if fallback_pixmap.isNull():
            logging.error(f"Fallback image '{fallback_path}' is also missing or invalid.")
        return fallback_pixmap

    def load_and_send(self, index):
        try:
            if 0 <= index < self.tables.getTableCount():
                path = self.tables.getImagePathByScreenname(index, self.screenname)
                if not os.path.exists(path):
                    logging.warning(f"Image path does not exist: {path}. Using fallback.")
                pixmap = self.getMissingImage(path)
                ba = QByteArray()
                buffer = QBuffer(ba)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "BMP")
                data = ba.data()
                shm = shared_memory.SharedMemory(create=True, size=len(data))
                shm.buf[:len(data)] = data
                self.shared_memory_refs[index] = shm
                self.cache[index] = shm.name
                self.result_queue.put((index, shm.name, len(data)))
                logging.info(f"Sent image {index} via shared memory {shm.name}")
        except Exception as e:
            logging.error("Image load failed!")
            raise

    def preload_surrounding(self, index):
        total = self.tables.getTableCount()
        if total <= self.max_cache:
            preload = list(range(total))
        else:
            start = max(index - 10, 0)
            end = min(index + 30, total)
            preload = list(range(start, end))
        self.cache_order = preload
        self.cache_cursor = 0
        logging.info(f"Preloading images from {preload[0]} to {preload[-1]}")

    def background_cache_step(self):
        try:
            if not hasattr(self, 'cache_order') or self.cache_cursor >= len(self.cache_order):
                return
            index = self.cache_order[self.cache_cursor]
            if index not in self.cache:
                self.load_to_shared_memory(index)

            self.cache_cursor += 1
            self.trim_cache()
        except Exception as e:
            logging.error("background_cache_step failed!")
            raise

    def load_to_shared_memory(self, index):
        try:
            if 0 <= index < self.tables.getTableCount():
                path = self.tables.getImagePathByScreenname(index, self.screenname)
                if not os.path.exists(path):
                    logging.warning(f"Image path does not exist: {path}. Using fallback.")
                pixmap = self.getMissingImage(path)
                ba = QByteArray()
                buffer = QBuffer(ba)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "BMP")
                data = ba.data()
                shm = shared_memory.SharedMemory(create=True, size=len(data))
                shm.buf[:len(data)] = data
                self.shared_memory_refs[index] = shm
                self.cache[index] = shm.name
                logging.info(f"Cached image {index} to shared memory {shm.name}")
        except Exception as e:
            logging.error("load_to_shared_memory failed!")
            raise

    def trim_cache(self):
        if len(self.cache) > self.max_cache:
            keys = sorted(self.cache.keys(), key=lambda k: abs(k - self.last_cached_index))
            for k in keys[self.max_cache:]:
                shm_name = self.cache.pop(k)
                try:
                    shm = self.shared_memory_refs.pop(k)
                    shm.close()
                    shm.unlink()
                    logging.info(f"Trimmed shared memory {shm_name}")
                except FileNotFoundError:
                    pass

    def cleanup(self):
        import multiprocessing.resource_tracker as rt

        for shm in self.shared_memory_refs.values():
            try:
                shm.close()
                shm.unlink()
                rt.unregister(shm._name, 'shared_memory')
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Error unlinking shared memory: {e}")
        self.shared_memory_refs.clear()

        # Clean up logo if it was loaded
        if hasattr(self, "logo_shm"):
            try:
                self.logo_shm.close()
                self.logo_shm.unlink()
                rt.unregister(self.logo_shm._name, 'shared_memory')
                logging.info("Unlinked logo shared memory")
            except FileNotFoundError:
                # Suppress this error completely — it's safe to ignore
                pass
            except Exception as e:
                logging.error(f"Error cleaning up logo shared memory: {e}")

    def load_next(self, index):
        next_index = index + 1
        if next_index < self.tables.getTableCount():
            self.load_and_send(next_index)
        else:
            logging.info(f"[{self.name}] No next image to load (index {next_index} out of range)")

    def load_previous(self, index):
        prev_index = index - 1
        if prev_index >= 0:
            self.load_and_send(prev_index)
        else:
            logging.info(f"[{self.name}] No previous image to load (index {prev_index} out of range)")

    def load_logo_image(self):
        try:
            pixmap = self.getMissingImage(logoImage)
            ba = QByteArray()
            buffer = QBuffer(ba)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buffer, "BMP")
            data = ba.data()
            shm = shared_memory.SharedMemory(create=True, size=len(data))
            shm.buf[:len(data)] = data
            self.logo_shm = shm  # ✅ keep separate
            self.result_queue.put(("logo", shm.name, len(data)))
            logging.info(f"Sent logo image via shared memory {shm.name}")

            # ✅ Trigger caching after logo
            self.preload_surrounding(0)

        except Exception as e:
            logging.error("Failed to load and display logo image")
            tb = traceback.format_exc()
            self.result_queue.put({"error": tb})