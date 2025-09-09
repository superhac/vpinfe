# custom_http_server.py
import http.server
from socketserver import ThreadingTCPServer
import threading
import os
from urllib.parse import unquote
from functools import partial
import posixpath

class CustomHTTPServer:
    class MultiDirHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        # Set debug True to print verbose logs
        debug = True

        def __init__(self, *args, mount_points=None, **kwargs):
            # normalize mount_points: ensure prefixes start+end with '/'
            mp = mount_points or {}
            normalized = {}
            for p, r in mp.items():
                prefix = p
                if not prefix.startswith('/'):
                    prefix = '/' + prefix
                if not prefix.endswith('/'):
                    prefix = prefix + '/'
                normalized[prefix] = os.path.abspath(r)
            self.mount_points = normalized
            if self.debug:
                print("[HTTP] Mount points:")
                for k, v in self.mount_points.items():
                    print(f"  {k} -> {v}")
            super().__init__(*args, **kwargs)

        def log_debug(self, *args):
            if self.debug:
                print("[HTTP]", *args)

        def translate_path(self, path):
            # 1) Strip query and fragment
            raw = path
            path = path.split('?', 1)[0].split('#', 1)[0]

            # 2) Unquote percent-encoding and normalize posix path (keeps forward slashes)
            path = unquote(path)
            path = posixpath.normpath(path)

            # Ensure leading slash for matching
            if not path.startswith('/'):
                path = '/' + path

            self.log_debug("Requested:", raw, "-> normalized:", path)

            # Iterate prefixes longest-first to avoid prefix shadowing
            for prefix, root in sorted(self.mount_points.items(), key=lambda x: -len(x[0])):
                if path == prefix.rstrip('/') or path.startswith(prefix):
                    rel = path[len(prefix):].lstrip('/')
                    # Normalize the relative part using posix rules, then split to join with os.path
                    rel_norm = posixpath.normpath('/' + rel).lstrip('/')
                    if rel_norm == '.':
                        rel_norm = ''
                    # Build a filesystem path safely
                    if rel_norm:
                        parts = rel_norm.split('/')
                        full_path = os.path.join(root, *parts)
                    else:
                        full_path = root
                    full_path = os.path.abspath(full_path)

                    # Prevent path escaping the root
                    try:
                        common = os.path.commonpath([root, full_path])
                    except ValueError:
                        # On differing drives (windows) commonpath can raise; treat as not allowed
                        self.log_debug("Drive mismatch or invalid path:", full_path)
                        return super().translate_path(path)

                    if common != root:
                        self.log_debug("Path traversal attempt blocked:", full_path, "not inside", root)
                        return super().translate_path(path)

                    # If the file or directory exists, return that path
                    if os.path.exists(full_path):
                        self.log_debug("Serving path:", full_path)
                        return full_path
                    else:
                        self.log_debug("Not found at:", full_path)
                        # Let base class produce a normal 404 (with our headers)
                        return super().translate_path(path)

            # No mount matched — fall back to default translate_path (cwd)
            self.log_debug("No matching mount point for", path)
            return super().translate_path(path)

        def end_headers(self):
            # Always add CORS headers to every response
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, Range")
            # Expose some headers so XHR/fetch can see content-length/range when needed
            self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(200, "OK")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, Range")
            self.end_headers()

        # Keep default logging behavior or override to quiet it:
        def log_message(self, fmt, *args):
            # use our debug printer so messages are consistent
            if self.debug:
                print("[HTTP] " + fmt % args)

    def __init__(self, mount_points):
        self.file_server = None
        self.mount_points = mount_points

    def start_file_server(self, port=8000):
        handler_class = partial(self.MultiDirHTTPRequestHandler, mount_points=self.mount_points)
        ThreadingTCPServer.allow_reuse_address = True
        self.file_server = ThreadingTCPServer(("", port), handler_class)
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

