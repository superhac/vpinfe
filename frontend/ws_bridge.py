"""
WebSocket bridge server that replaces pywebview's JS API bridge.

Each Chromium window connects via WebSocket with its window name as a query param:
  ws://127.0.0.1:8002?window=bg

JS→Python: API call requests with unique IDs, responses sent back
Python→JS: Event push messages for inter-window communication
"""

import asyncio
import json
import threading
import traceback
from urllib.parse import urlparse, parse_qs

import websockets


class WebSocketBridge:
    """WebSocket server that bridges JavaScript ↔ Python API calls."""

    # Public API methods that JS is allowed to call
    ALLOWED_METHODS = {
        'get_my_window_name',
        'close_app',
        'get_monitors',
        'get_tables',
        'get_collections',
        'set_tables_by_collection',
        'save_filter_collection',
        'get_current_filter_state',
        'get_current_sort_state',
        'get_current_collection',
        'get_filter_letters',
        'get_filter_themes',
        'get_filter_types',
        'get_filter_manufacturers',
        'get_filter_years',
        'apply_filters',
        'apply_sort',
        'reset_filters',
        'console_out',
        'get_joymaping',
        'set_button_mapping',
        'launch_table',
        'build_metadata',
        'get_theme_config',
        'get_theme_name',
        'get_theme_assets_port',
        'get_theme_index_page',
        'send_event',
        'send_event_all_windows',
        'send_event_all_windows_incself',
        'playSound',
    }

    def __init__(self, port=8002):
        self.port = port
        self._api_instances = {}       # {window_name: api_instance}
        self._connections = {}         # {window_name: websocket}
        self._loop = None
        self._thread = None
        self._server = None
        self._stop_event = threading.Event()

    def register_api(self, window_name, api_instance):
        """Register an API instance for a window name."""
        self._api_instances[window_name] = api_instance

    def start(self):
        """Start the WebSocket server in a daemon thread."""
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        # Wait briefly for the server to be ready
        for _ in range(50):
            if self._loop is not None and self._server is not None:
                break
            import time
            time.sleep(0.05)
        print(f"[WS] WebSocket bridge started on ws://127.0.0.1:{self.port}/")

    def _run_server(self):
        """Run the async event loop in the daemon thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        """Start the WebSocket server and run until stopped."""
        self._server = await websockets.serve(
            self._handle_connection,
            "127.0.0.1",
            self.port,
            max_size=10 * 1024 * 1024,  # 10MB max message size for large table data
        )
        # Wait until stop is signaled
        while not self._stop_event.is_set():
            await asyncio.sleep(0.5)
        self._server.close()
        await self._server.wait_closed()

    async def _handle_connection(self, websocket):
        """Handle a new WebSocket connection from a Chromium window."""
        # Parse window name from query params
        parsed = urlparse(websocket.request.path if hasattr(websocket.request, 'path') else str(websocket.request))
        params = parse_qs(parsed.query)
        window_name = params.get('window', ['unknown'])[0]

        print(f"[WS] Window '{window_name}' connected")
        self._connections[window_name] = websocket

        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                    await self._dispatch(window_name, websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Invalid JSON'
                    }))
                except Exception as e:
                    print(f"[WS] Error handling message from '{window_name}': {e}")
                    traceback.print_exc()
        except websockets.exceptions.ConnectionClosed:
            print(f"[WS] Window '{window_name}' disconnected")
        finally:
            if self._connections.get(window_name) is websocket:
                del self._connections[window_name]

    async def _dispatch(self, window_name, websocket, data):
        """Dispatch an incoming message from JS."""
        msg_type = data.get('type')

        if msg_type == 'api_call':
            await self._handle_api_call(window_name, websocket, data)
        else:
            print(f"[WS] Unknown message type from '{window_name}': {msg_type}")

    async def _handle_api_call(self, window_name, websocket, data):
        """Handle a JS→Python API call."""
        call_id = data.get('id')
        method = data.get('method')
        args = data.get('args', [])

        if method not in self.ALLOWED_METHODS:
            await websocket.send(json.dumps({
                'type': 'api_response',
                'id': call_id,
                'error': f'Method not allowed: {method}'
            }))
            return

        api = self._api_instances.get(window_name)
        if api is None:
            await websocket.send(json.dumps({
                'type': 'api_response',
                'id': call_id,
                'error': f'No API instance for window: {window_name}'
            }))
            return

        fn = getattr(api, method, None)
        if fn is None or not callable(fn):
            await websocket.send(json.dumps({
                'type': 'api_response',
                'id': call_id,
                'error': f'Method not found: {method}'
            }))
            return

        try:
            # Run the API method in a thread to avoid blocking the event loop
            result = await asyncio.to_thread(fn, *args)

            await websocket.send(json.dumps({
                'type': 'api_response',
                'id': call_id,
                'result': result
            }))
        except websockets.exceptions.ConnectionClosed:
            pass  # Client disconnected before response (e.g. close_app)
        except Exception as e:
            print(f"[WS] API call error: {method}({args}) -> {e}")
            traceback.print_exc()
            try:
                await websocket.send(json.dumps({
                    'type': 'api_response',
                    'id': call_id,
                    'error': str(e)
                }))
            except websockets.exceptions.ConnectionClosed:
                pass

    # -----------------------------------------------------------
    # Python-callable methods for pushing events to browsers
    # -----------------------------------------------------------

    def send_event(self, window_name, message):
        """Send an event to a specific window's browser."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._send_event_async(window_name, message),
            self._loop
        )

    def send_event_all(self, message, exclude=None):
        """Broadcast an event to all connected windows, optionally excluding one."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._send_event_all_async(message, exclude=exclude, forward_iframe=False),
            self._loop
        )

    def send_event_all_with_iframe(self, message):
        """Broadcast an event to all windows, including iframe forwarding."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._send_event_all_async(message, exclude=None, forward_iframe=True),
            self._loop
        )

    async def _send_event_async(self, window_name, message):
        """Internal async: send event to one window."""
        ws = self._connections.get(window_name)
        if ws is None:
            return
        try:
            await ws.send(json.dumps({
                'type': 'event',
                'message': message
            }))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def _send_event_all_async(self, message, exclude=None, forward_iframe=False):
        """Internal async: broadcast event to windows."""
        payload = json.dumps({
            'type': 'event',
            'message': message,
            'forward_iframe': forward_iframe
        })
        for name, ws in list(self._connections.items()):
            if exclude and name == exclude:
                continue
            try:
                await ws.send(payload)
            except websockets.exceptions.ConnectionClosed:
                pass

    def stop(self):
        """Stop the WebSocket server."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        print("[WS] WebSocket bridge stopped.")
