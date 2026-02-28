import errno
import os
import queue
import signal
import struct
import subprocess
import threading
import time
from pathlib import Path

from nicegui import ui

try:
    import fcntl
    import pty
    import termios
except ImportError:
    fcntl = None
    pty = None
    termios = None

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SESSIONS = {}
_DISCONNECT_HOOKED = set()


class _TerminalSession:
    def __init__(self) -> None:
        self.master_fd = None
        self.process = None
        self.output_queue = queue.Queue()
        self.closed = False
        self._reader_thread = None

    def start(self) -> None:
        if not (pty and fcntl and termios):
            raise RuntimeError('PTY terminal is not supported on this platform.')
        shell = os.environ.get('SHELL', '/bin/bash')
        master_fd, slave_fd = pty.openpty()

        self.process = subprocess.Popen(
            [shell, '-i'],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(_PROJECT_ROOT),
            start_new_session=True,
            env=os.environ.copy(),
        )
        os.close(slave_fd)
        self.master_fd = master_fd

        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        while not self.closed:
            if self.process and self.process.poll() is not None:
                break
            try:
                data = os.read(self.master_fd, 4096)
                if data:
                    self.output_queue.put(data.decode(errors='replace'))
                    continue
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
            time.sleep(0.02)
        exit_code = self.process.poll() if self.process else None
        self.output_queue.put(f'\r\n[process exited with code {exit_code}]\r\n')

    def write_input(self, data: str) -> None:
        if self.closed or self.master_fd is None:
            return
        try:
            os.write(self.master_fd, data.encode())
        except OSError:
            pass

    def resize(self, rows: int, cols: int) -> None:
        if self.closed or self.master_fd is None:
            return
        winsize = struct.pack('HHHH', rows, cols, 0, 0)
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except OSError:
                pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None


def _close_session(client_id: str) -> None:
    session = _SESSIONS.pop(client_id, None)
    if session:
        session.close()
    _DISCONNECT_HOOKED.discard(client_id)


def render_panel(tab=None):
    client = ui.context.client
    client_id = client.id

    if client_id in _SESSIONS:
        _close_session(client_id)

    if not (pty and fcntl and termios):
        with ui.column().classes('w-full'):
            with ui.card().classes('w-full p-4'):
                ui.label('Terminal is not supported on this platform.').classes('text-red-400')
        return

    session = _TerminalSession()
    _SESSIONS[client_id] = session
    try:
        session.start()
    except Exception as e:
        _close_session(client_id)
        with ui.column().classes('w-full'):
            with ui.card().classes('w-full p-4'):
                ui.label(f'Failed to start terminal: {e}').classes('text-red-400')
        return

    if client_id not in _DISCONNECT_HOOKED:
        client.on_disconnect(lambda: _close_session(client_id))
        _DISCONNECT_HOOKED.add(client_id)

    with ui.column().classes('w-full'):
        with ui.card().classes('w-full mb-4').style(
            'background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); border-radius: 12px;'
        ):
            with ui.row().classes('w-full items-center p-4 gap-4'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('terminal', size='32px').classes('text-white')
                    ui.label('Terminal').classes('text-2xl font-bold text-white')

        term = ui.xterm({
            'cursorBlink': True,
            'fontSize': 14,
            'fontFamily': 'Menlo, Monaco, Consolas, "Liberation Mono", monospace',
            'theme': {
                'background': '#0b1220',
                'foreground': '#e2e8f0',
            },
            'scrollback': 5000,
        }).classes('w-full')
        term.style('height: calc(100vh - 260px); min-height: 420px; border: 1px solid #334155; border-radius: 8px;')

    term.writeln(f'Connected to shell in {_PROJECT_ROOT}')

    def handle_data(e):
        session.write_input(e.data)

    term.on_data(handle_data)

    def flush_output():
        if session.closed:
            return
        chunks = []
        while len(chunks) < 50:
            try:
                chunks.append(session.output_queue.get_nowait())
            except queue.Empty:
                break
        if chunks:
            term.write(''.join(chunks))

    async def fit_and_resize():
        await term.fit()
        rows = await term.get_rows()
        cols = await term.get_columns()
        session.resize(rows, cols)

    ui.timer(0.05, flush_output)
    ui.timer(0.5, fit_and_resize, once=True)
