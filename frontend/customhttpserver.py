# custom_http_server.py
import http.server
import logging
from socketserver import ThreadingTCPServer
import threading
import os
import mimetypes
from urllib.parse import unquote, urlsplit
from functools import partial
import posixpath
import re

import requests


logger = logging.getLogger("vpinfe.frontend.customhttpserver")

class CustomHTTPServer:
    class MultiDirHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        # Set debug True to print verbose logs
        debug = False
        PINBALL_PRIMER_PREFIX = "https://pinballprimer.github.io/"

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
                logger.debug("[HTTP] Mount points:")
                for k, v in self.mount_points.items():
                    logger.debug("  %s -> %s", k, v)
            super().__init__(*args, **kwargs)

        def log_debug(self, *args):
            if self.debug:
                logger.debug("[HTTP] %s", " ".join(str(arg) for arg in args))

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
            # cache busting
            #self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            #self.send_header('Pragma', 'no-cache')
            #self.send_header('Expires', '0')
            # Always add CORS headers to every response
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, Range")
            # Expose some headers so XHR/fetch can see content-length/range when needed
            self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")
            super().end_headers()

        @classmethod
        def _is_allowed_pinball_primer_url(cls, url):
            if not isinstance(url, str):
                return False
            normalized = url.strip()
            if not normalized.startswith(cls.PINBALL_PRIMER_PREFIX):
                return False
            parsed = urlsplit(normalized)
            return parsed.scheme == "https" and parsed.netloc == "pinballprimer.github.io"

        @classmethod
        def _inject_base_tag(cls, html_text, base_href):
            if not isinstance(html_text, str):
                html_text = str(html_text or "")
            base_tag = f'<base href="{base_href}">'
            if re.search(r"<base\s", html_text, flags=re.IGNORECASE):
                return html_text

            head_match = re.search(r"<head[^>]*>", html_text, flags=re.IGNORECASE)
            if head_match:
                insert_at = head_match.end()
                return f"{html_text[:insert_at]}{base_tag}{html_text[insert_at:]}"

            return f"<head>{base_tag}</head>{html_text}"

        @classmethod
        def _build_pinball_primer_error_html(cls, message, requested_url=""):
            safe_message = str(message or "Unable to load Pinball Primer tutorial.")
            safe_url = str(requested_url or "")
            return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Pinball Primer Tutorial Error</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #111827;
        color: #e5eefc;
        font-family: sans-serif;
      }}
      .card {{
        max-width: 48rem;
        padding: 2rem;
        border-radius: 1rem;
        background: rgba(15, 23, 42, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.28);
        box-shadow: 0 0 24px rgba(15, 23, 42, 0.35);
      }}
      h1 {{ margin: 0 0 1rem; font-size: 1.5rem; }}
      p {{ margin: 0.5rem 0; line-height: 1.5; }}
      code {{
        display: block;
        margin-top: 1rem;
        padding: 0.75rem 1rem;
        background: rgba(15, 23, 42, 0.9);
        border-radius: 0.75rem;
        overflow-wrap: anywhere;
        color: #93c5fd;
      }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Pinball Primer Tutorial Unavailable</h1>
      <p>{safe_message}</p>
      <p>Press <strong>T</strong> or your Back button to close this overlay.</p>
      <code>{safe_url}</code>
    </div>
  </body>
</html>
"""

        def _send_pinball_primer_html(self, status_code, html_text):
            body = html_text.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionResetError, BrokenPipeError):
                return

        def _serve_pinball_primer_proxy(self):
            query = urlsplit(self.path).query
            requested_url = ""
            for pair in query.split("&"):
                if not pair:
                    continue
                key, _, value = pair.partition("=")
                if key == "url":
                    requested_url = unquote(value)
                    break

            if not self._is_allowed_pinball_primer_url(requested_url):
                self._send_pinball_primer_html(
                    403,
                    self._build_pinball_primer_error_html(
                        "Only https://pinballprimer.github.io/ URLs are allowed.",
                        requested_url,
                    ),
                )
                return

            try:
                response = requests.get(
                    requested_url,
                    timeout=15,
                    headers={"User-Agent": "VPinFE PinballPrimer Proxy"},
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.warning("Pinball Primer proxy fetch failed for %s: %s", requested_url, exc)
                self._send_pinball_primer_html(
                    502,
                    self._build_pinball_primer_error_html(
                        "The Pinball Primer page could not be downloaded right now.",
                        requested_url,
                    ),
                )
                return

            html_text = self._inject_base_tag(response.text, requested_url)
            self._send_pinball_primer_html(200, html_text)

        def _serve_app_bootstrap(self, window_name):
            window_labels = {
                "bg": "BG",
                "dmd": "DMD",
                "table": "Table",
            }
            window_label = window_labels.get(window_name)
            if window_label is None:
                self.send_error(404, "Unknown app window")
                return

            html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>VPinFE {window_label}</title>
    <script src="/web/common/vpinfe-core.js"></script>
    <script>
      const vpin = new VPinFECore();
      vpin.init();

      vpin.ready.then(async () => {{
        const params = window.location.search;
        const splashEnabledRaw = await vpin.call("get_splashscreen_enabled");
        const splashEnabledNormalized = String(splashEnabledRaw).trim().toLowerCase();
        const splashDisabled = ["false", "0", "no", "off"].includes(splashEnabledNormalized);

        let location = await vpin.call("get_theme_index_page");
        if (!splashDisabled) {{
          location = `/web/splash.html?window={window_name}`;
        }}

        if (params) {{
          const separator = location.includes("?") ? "&" : "?";
          const extraParams = params.substring(1);
          if (extraParams) {{
            location += separator + extraParams;
          }}
        }}

        window.location.replace(location);
      }});
    </script>
  </head>
  <body style="margin: 0; background: black;"></body>
</html>
"""
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionResetError, BrokenPipeError):
                return

        def do_GET(self):
            """Override to handle Range requests for video streaming."""
            request_path = urlsplit(self.path).path
            if request_path.startswith("/app/"):
                window_name = request_path[len("/app/"):].strip("/")
                self._serve_app_bootstrap(window_name)
                return
            if request_path == "/proxy/pinballprimer":
                self._serve_pinball_primer_proxy()
                return

            range_header = self.headers.get('Range')
            if not range_header:
                # No Range header — use default behavior
                try:
                    super().do_GET()
                except (ConnectionResetError, BrokenPipeError):
                    # Client closed connection while we were writing the response.
                    return
                return

            # Resolve the file path
            path = self.translate_path(self.path)
            if not os.path.isfile(path):
                self.send_error(404, "File not found")
                return

            file_size = os.path.getsize(path)

            # Parse "bytes=START-END" or "bytes=START-"
            try:
                range_spec = range_header.replace('bytes=', '')
                parts = range_spec.split('-', 1)
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
            except (ValueError, IndexError):
                self.send_error(416, "Requested Range Not Satisfiable")
                return

            if start >= file_size or start > end:
                self.send_error(416, "Requested Range Not Satisfiable")
                return

            # Clamp end to file boundary
            end = min(end, file_size - 1)
            content_length = end - start + 1
            ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'

            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(content_length))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            try:
                with open(path, 'rb') as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (ConnectionResetError, BrokenPipeError):
                pass  # Client closed connection, that's fine

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
                logger.debug("[HTTP] " + fmt % args)

    def __init__(self, mount_points):
        self.file_server = None
        self.mount_points = mount_points

    def start_file_server(self, port=8000):
        handler_class = partial(self.MultiDirHTTPRequestHandler, mount_points=self.mount_points)
        ThreadingTCPServer.allow_reuse_address = True
        self.file_server = ThreadingTCPServer(("", port), handler_class)
        threading.Thread(target=self.file_server.serve_forever, daemon=True).start()
        logger.info("Serving on http://127.0.0.1:%s/", port)

    def stop_file_server(self):
        if self.file_server:
            self.file_server.shutdown()
            self.file_server.server_close()
            logger.info("File server stopped.")
            self.file_server = None

    def on_closed(self):
        self.stop_file_server()
