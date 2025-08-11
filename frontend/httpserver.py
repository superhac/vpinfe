import http.server
import socketserver
import threading
import os
from urllib.parse import unquote
from functools import partial


class HTTPServer:

    class MultiDirHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, mount_points=None, **kwargs):
            print("[DEBUG] Handler initialized")
            self.mount_points = mount_points or {}
            super().__init__(*args, **kwargs)

        def translate_path(self, path):
            path = unquote(path)
            print(f"[HTTP] Requested: {path}")
            for prefix, root in self.mount_points.items():
                # Match if path == /web or starts with /web/
                if path == prefix.rstrip('/') or path.startswith(prefix):
                    relative_path = path[len(prefix):].lstrip('/')
                    full_path = os.path.join(root, relative_path)
                    print(f"[HTTP] Serving: {full_path}")
                    return full_path
            print("[HTTP] No matching mount point, serving /dev/null")
            return "/dev/null"

        def log_message(self, format, *args):
            pass  # Silence default logging

    def __init__(self, mount_points):
        self.file_server = None
        self.mount_points = mount_points

    def start_file_server(self, port=8000):
        handler_class = partial(self.MultiDirHTTPRequestHandler, mount_points=self.mount_points)
        socketserver.TCPServer.allow_reuse_address = True
        self.file_server = socketserver.TCPServer(("", port), handler_class)
        threading.Thread(target=self.file_server.serve_forever, daemon=True).start()
        print(f"[INFO] Serving on http://0.0.0.0:{port}/")

    def stop_file_server(self):
        if self.file_server:
            self.file_server.shutdown()
            self.file_server.server_close()
            print("[INFO] File server stopped.")
            self.file_server = None

    def on_closed(self):
        self.stop_file_server()
