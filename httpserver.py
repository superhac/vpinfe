import http.server
import socketserver
import threading
import os
from urllib.parse import unquote

class HTTPServer:

    class MultiDirHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.mount_points = kwargs.pop('mount_points', {})
            super().__init__(*args, **kwargs)

        def translate_path(self, path):
            path = unquote(path)
            for prefix, root in self.mount_points.items():
                if path.startswith(prefix):
                    return os.path.join(root, path[len(prefix):])
            return "/dev/null"

        def log_message(self, format, *args):
            pass  # Silence logs

    def __init__(self, mount_points):
        self.file_server = None
        self.mount_points = mount_points

    def start_file_server(self, port=8000):
        # Handler factory to inject instance mount_points
        def handler_factory(*args, **kwargs):
            return self.MultiDirHTTPRequestHandler(*args, mount_points=self.mount_points, **kwargs)

        socketserver.TCPServer.allow_reuse_address = True
        self.file_server = socketserver.TCPServer(("", port), handler_factory)
        threading.Thread(target=self.file_server.serve_forever, daemon=True).start()
        print(f"Serving only on http://127.0.0.1:{port}/")

    def stop_file_server(self):
        if self.file_server:
            self.file_server.shutdown()
            self.file_server.server_close()
            print("File server stopped.")
            self.file_server = None

    def on_closed(self):
        self.stop_file_server()

