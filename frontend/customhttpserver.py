import http.server
import socketserver
import threading
import os
from urllib.parse import unquote
from functools import partial


class CustomHTTPServer:
    class MultiDirHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, mount_points=None, **kwargs):
            self.mount_points = mount_points or {}
            super().__init__(*args, **kwargs)

        def translate_path(self, path):
            path = unquote(path)
            print(f"[HTTP] Requested: {path}")
            for prefix, root in self.mount_points.items():
                # Match if path == /prefix or starts with /prefix/
                if path == prefix.rstrip('/') or path.startswith(prefix):
                    relative_path = path[len(prefix):].lstrip('/')
                    full_path = os.path.join(root, relative_path)
                    print(f"[HTTP] Serving: {full_path}")
                    return full_path
            print("[HTTP] No matching mount point, serving /dev/null")
            return "/dev/null"

        def end_headers(self):
            # ✅ Add CORS headers
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
            super().end_headers()

        def do_OPTIONS(self):
            # ✅ Handle preflight requests
            self.send_response(200, "ok")
            self.end_headers()

        def log_message(self, format, *args):
            # Silence default logging
            pass

    def __init__(self, mount_points):
        self.file_server = None
        self.mount_points = mount_points

    def start_file_server(self, port=8000):
        handler_class = partial(self.MultiDirHTTPRequestHandler, mount_points=self.mount_points)
        socketserver.TCPServer.allow_reuse_address = True
        self.file_server = socketserver.TCPServer(("", port), handler_class)
        threading.Thread(target=self.file_server.serve_forever, daemon=True).start()
        print(f"[INFO] Serving on http://127.0.0.1:{port}/")

    def stop_file_server(self):
        if self.file_server:
            self.file_server.shutdown()
            self.file_server.server_close()
            print("[INFO] File server stopped.")
            self.file_server = None

    def on_closed(self):
        self.stop_file_server()
