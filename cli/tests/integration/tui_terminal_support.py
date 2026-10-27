"""Bounded native PTY/ConPTY process driver; no application/model imports."""

from __future__ import annotations

from contextlib import contextmanager
import codecs
import ctypes as ct
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
import unicodedata

if os.name == "posix":
    import fcntl
    import pty
    import termios


def executable():
    binary = os.environ.get("WORKSTREAM_CLI_EXECUTABLE")
    assert binary and Path(binary).is_file(), "build and set WORKSTREAM_CLI_EXECUTABLE"
    return binary


def environment(origin, token, extra=None):
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "LANG", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    env.update(
        WORKSTREAM_API_URL=origin,
        WORKSTREAM_TOKEN=token,
        TERM="xterm-256color",
    )
    env.update(extra or {})
    return env


class Terminal:
    """A real child on a PTY with a bounded, minimal VT screen observer.

    The screen observer only handles renderer movement/erase/SGR, never executes
    OSC. Raw output is retained too, so hostile terminal controls cannot hide
    behind a screen parser that ignores them.
    """

    def __init__(
        self,
        origin,
        token,
        *args,
        columns=120,
        rows=40,
        extra_env=None,
        light_background=False,
    ):
        assert os.name == "posix", "unsupported native terminal host"
        self.master, self.slave = pty.openpty()
        self.original = termios.tcgetattr(self.slave)
        self._screen_setup(columns, rows, light_background)
        self.resize(columns, rows, notify=False)
        self.process = subprocess.Popen(  # noqa: S603 - built binary, fixed test argv
            [executable(), "tui", *args],
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            env=environment(origin, token, extra_env),
            start_new_session=True,
        )

    def _screen_setup(self, columns, rows, light_background=False):
        self.columns, self.rows = columns, rows
        self.light_background = light_background
        self.background_queries = 0
        self.raw = bytearray()
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.pending = ""
        self.sent_after = None
        self.x = self.y = 0
        self.cells = [[" "] * columns for _ in range(rows)]
        self.scroll_top, self.scroll_bottom = 0, rows - 1

    def _write(self, data):
        os.write(self.master, data)

    def resize(self, columns, rows, *, notify=True):
        fcntl.ioctl(
            self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
        )
        self.columns, self.rows = columns, rows
        if notify:
            self.cells = [[" "] * columns for _ in range(rows)]
            self.x = self.y = 0
            self.scroll_top, self.scroll_bottom = 0, rows - 1
            self.process.send_signal(signal.SIGWINCH)

    @property
    def screen(self):
        return "\n".join("".join(row).rstrip() for row in self.cells)

    def _render(self, text):
        self.pending += text
        while self.pending:
            if self.pending.startswith("\x1b"):
                match = re.match(r"\x1b\[([0-?]*)([ -/]*)([@-~])", self.pending)
                if match:
                    self.pending = self.pending[match.end() :]
                    params, _, command = match.groups()
                    values = [
                        int(part) if part.isdecimal() else 0
                        for part in params.lstrip("?<>=!").split(";")
                    ]
                    n = values[0] or 1
                    if command in {"H", "f"}:
                        self.y = min(self.rows - 1, n - 1)
                        self.x = min(
                            self.columns - 1,
                            (values[1] or 1) - 1 if len(values) > 1 else 0,
                        )
                    elif command == "A":
                        self.y = max(0, self.y - n)
                    elif command == "B":
                        self.y = min(self.rows - 1, self.y + n)
                    elif command == "d":
                        self.y = min(self.rows - 1, n - 1)
                    elif command in {"E", "F"}:
                        self.y = (
                            min(self.rows - 1, self.y + n)
                            if command == "E"
                            else max(0, self.y - n)
                        )
                        self.x = 0
                    elif command == "C":
                        self.x = min(self.columns - 1, self.x + n)
                    elif command == "D":
                        self.x = max(0, self.x - n)
                    elif command == "G":
                        self.x = min(self.columns - 1, n - 1)
                    elif command == "r" and not params.startswith(("?", "<", ">", "=")):
                        top = (values[0] or 1) - 1
                        bottom = (
                            (values[1] or self.rows) if len(values) > 1 else self.rows
                        ) - 1
                        if 0 <= top < bottom < self.rows:
                            self.scroll_top, self.scroll_bottom = top, bottom
                            self.x = self.y = 0
                    elif command == "T":
                        # Bubble Tea emits SD inside DECSTBM to shift only the
                        # detail viewport; header/status rows must stay put.
                        top, bottom = self.scroll_top, self.scroll_bottom
                        amount = min(n, bottom - top + 1)
                        retained = self.cells[top : bottom + 1 - amount]
                        self.cells[top : bottom + 1] = [
                            [" "] * self.columns for _ in range(amount)
                        ] + retained
                    elif command == "P":
                        deleted = min(n, self.columns - self.x)
                        row = self.cells[self.y]
                        row[self.x :] = row[self.x + deleted :] + [" "] * deleted
                    elif command == "J":
                        if values[0] in {2, 3}:
                            self.cells = [
                                [" "] * self.columns for _ in range(self.rows)
                            ]
                        else:
                            self.cells[self.y][self.x :] = [" "] * (
                                self.columns - self.x
                            )
                            for row in range(self.y + 1, self.rows):
                                self.cells[row] = [" "] * self.columns
                    elif command == "K":
                        start, end = (
                            (0, self.columns)
                            if values[0] == 2
                            else (self.x, self.columns)
                        )
                        self.cells[self.y][start:end] = [" "] * (end - start)
                    elif command == "n" and params == "6":
                        column = min(self.x + 1, self.columns)
                        self._write(f"\x1b[{self.y + 1};{column}R".encode())
                    continue
                if self.pending.startswith("\x1b]"):
                    match = re.match(r"\x1b\].*?(?:\x07|\x1b\\)", self.pending, re.S)
                    if not match:
                        return
                    sequence = match.group()
                    self.pending = self.pending[match.end() :]
                    if sequence.startswith("\x1b]11;?"):
                        self.background_queries += 1
                        if self.light_background is not None:
                            background = (
                                "ffff/ffff/ffff"
                                if self.light_background
                                else "0000/0000/0000"
                            )
                            self._write(f"\x1b]11;rgb:{background}\x1b\\".encode())
                    elif sequence.startswith("\x1b]10;?"):
                        self._write(b"\x1b]10;rgb:ffff/ffff/ffff\x1b\\")
                    continue
                if len(self.pending) < 3 or self.pending.startswith("\x1b["):
                    return
                self.pending = self.pending[2:]
                continue
            character, self.pending = self.pending[0], self.pending[1:]
            if character == "\r":
                self.x = 0
            elif character == "\t":
                self.x = min(self.columns - 1, (self.x // 8 + 1) * 8)
            elif character == "\n":
                if self.y == self.scroll_bottom:
                    self.cells.pop(self.scroll_top)
                    self.cells.insert(self.scroll_bottom, [" "] * self.columns)
                else:
                    self.y = min(self.rows - 1, self.y + 1)
            elif character == "\b":
                self.x = max(0, self.x - 1)
            elif character >= " " and not unicodedata.combining(character):
                if self.x >= self.columns:
                    self.x = 0
                    self.y = min(self.rows - 1, self.y + 1)
                self.cells[self.y][self.x] = character
                self.x += (
                    2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
                )

    def pump(self, seconds=0.1):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [self.master], [], [], max(0, deadline - time.monotonic())
            )
            if not ready:
                break
            try:
                data = os.read(self.master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not data:
                break
            self.raw.extend(data)
            assert len(self.raw) < 4 * 1024 * 1024, "unbounded terminal output"
            self._render(self.decoder.decode(data))

    def wait(self, text, timeout=10):
        deadline = time.monotonic() + timeout
        while (
            text not in self.screen
            or (self.sent_after is not None and len(self.raw) <= self.sent_after)
        ) and time.monotonic() < deadline:
            self.pump()
            returncode = self.process.poll()
            assert returncode is None, (
                f"TUI exited (return code {returncode}): {self.screen}"
            )
        assert text in self.screen, f"missing {text!r} on screen:\n{self.screen}"
        assert self.sent_after is None or len(self.raw) > self.sent_after, (
            "no new terminal frame after input"
        )
        self.sent_after = None
        return self.screen

    def send(self, keys):
        # Observe output already queued before this input. Otherwise an expect
        # could mistake the previous project/detail's frame for the new result.
        self.pump(0.02)
        self.sent_after = len(self.raw)
        self._write(keys.encode() if isinstance(keys, str) else keys)

    def quit(self, key="q"):
        self.send(key)
        self.wait_exit()

    def wait_exit(self, expected=0):
        deadline = time.monotonic() + 10
        while self.process.poll() is None and time.monotonic() < deadline:
            self.pump()
        assert self.process.poll() == expected, f"TUI exit mismatch: {self.screen}"
        self.pump()
        self._assert_restored()

    def _assert_restored(self):
        if sys.platform == "darwin":
            # XNU sets transient PENDIN on raw -> canonical restoration. Its
            # ttyselect(FREAD) -> ttnread -> ttypend path settles that kernel
            # state without consuming input or changing application flags.
            # See xnu-11417.140.69/bsd/kern/tty.c in apple-oss-distributions/xnu.
            select.select([self.slave], [], [], 0)
        restored = termios.tcgetattr(self.slave)
        # Only bounded OS terminal fields reach this diagnostic, never output,
        # credentials, or server text. Keep the exact restoration comparison.
        assert restored == self.original, (
            "terminal settings were not restored; "
            f"before_flags_speeds={self.original[:6]}; "
            f"after_flags_speeds={restored[:6]}; "
            f"before_cc={[v if isinstance(v, int) else ord(v) for v in self.original[6]]}; "
            f"after_cc={[v if isinstance(v, int) else ord(v) for v in restored[6]]}; "
            f"before_int_cc={[i for i, v in enumerate(self.original[6]) if isinstance(v, int)]}; "
            f"after_int_cc={[i for i, v in enumerate(restored[6]) if isinstance(v, int)]}"
        )
        self._assert_cursor_and_screen_restored()

    def _assert_cursor_and_screen_restored(self):
        for enabled, disabled in (
            (b"\x1b[?25l", b"\x1b[?25h"),
            (b"\x1b[?1049h", b"\x1b[?1049l"),
        ):
            if enabled in self.raw:
                assert self.raw.rfind(disabled) > self.raw.rfind(enabled), (
                    "terminal mode left active"
                )

    def assert_no_terminal_controls(self):
        assert b"\x1b" not in self.raw

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        os.close(self.master)
        os.close(self.slave)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


if os.name == "nt":
    from ctypes import wintypes as wt

    class _Coord(ct.Structure):
        _fields_ = [("X", ct.c_short), ("Y", ct.c_short)]

    class _StartupInfo(ct.Structure):
        _fields_ = [
            ("cb", wt.DWORD),
            ("lpReserved", wt.LPWSTR),
            ("lpDesktop", wt.LPWSTR),
            ("lpTitle", wt.LPWSTR),
            ("dwX", wt.DWORD),
            ("dwY", wt.DWORD),
            ("dwXSize", wt.DWORD),
            ("dwYSize", wt.DWORD),
            ("dwXCountChars", wt.DWORD),
            ("dwYCountChars", wt.DWORD),
            ("dwFillAttribute", wt.DWORD),
            ("dwFlags", wt.DWORD),
            ("wShowWindow", wt.WORD),
            ("cbReserved2", wt.WORD),
            ("lpReserved2", ct.POINTER(wt.BYTE)),
            ("hStdInput", wt.HANDLE),
            ("hStdOutput", wt.HANDLE),
            ("hStdError", wt.HANDLE),
        ]

    class _StartupInfoEx(ct.Structure):
        _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", ct.c_void_p)]

    class _ProcessInfo(ct.Structure):
        _fields_ = [
            ("hProcess", wt.HANDLE),
            ("hThread", wt.HANDLE),
            ("dwProcessId", wt.DWORD),
            ("dwThreadId", wt.DWORD),
        ]

    class _BasicJobLimits(ct.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ct.c_int64),
            ("PerJobUserTimeLimit", ct.c_int64),
            ("LimitFlags", wt.DWORD),
            ("MinimumWorkingSetSize", ct.c_size_t),
            ("MaximumWorkingSetSize", ct.c_size_t),
            ("ActiveProcessLimit", wt.DWORD),
            ("Affinity", ct.c_size_t),
            ("PriorityClass", wt.DWORD),
            ("SchedulingClass", wt.DWORD),
        ]

    class _IoCounters(ct.Structure):
        _fields_ = [
            (name, ct.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JobLimits(ct.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicJobLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ct.c_size_t),
            ("JobMemoryLimit", ct.c_size_t),
            ("PeakProcessMemoryUsed", ct.c_size_t),
            ("PeakJobMemoryUsed", ct.c_size_t),
        ]

    class _CursorInfo(ct.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("bVisible", wt.BOOL)]

    class _WindowsAPI:
        """Explicit signatures: default ctypes int results truncate x64 handles."""

        def __init__(self):
            self.dll = ct.WinDLL("kernel32", use_last_error=True)
            pointer = ct.c_void_p
            signatures = {
                "CreatePipe": (
                    wt.BOOL,
                    [ct.POINTER(wt.HANDLE), ct.POINTER(wt.HANDLE), pointer, wt.DWORD],
                ),
                "CloseHandle": (wt.BOOL, [wt.HANDLE]),
                "CreatePseudoConsole": (
                    ct.c_long,
                    [_Coord, wt.HANDLE, wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)],
                ),
                "ResizePseudoConsole": (ct.c_long, [wt.HANDLE, _Coord]),
                "ClosePseudoConsole": (None, [wt.HANDLE]),
                "InitializeProcThreadAttributeList": (
                    wt.BOOL,
                    [pointer, wt.DWORD, wt.DWORD, ct.POINTER(ct.c_size_t)],
                ),
                "UpdateProcThreadAttribute": (
                    wt.BOOL,
                    [
                        pointer,
                        wt.DWORD,
                        ct.c_size_t,
                        pointer,
                        ct.c_size_t,
                        pointer,
                        pointer,
                    ],
                ),
                "DeleteProcThreadAttributeList": (None, [pointer]),
                "CreateProcessW": (
                    wt.BOOL,
                    [
                        wt.LPCWSTR,
                        wt.LPWSTR,
                        pointer,
                        pointer,
                        wt.BOOL,
                        wt.DWORD,
                        pointer,
                        wt.LPCWSTR,
                        ct.POINTER(_StartupInfoEx),
                        ct.POINTER(_ProcessInfo),
                    ],
                ),
                "CreateJobObjectW": (wt.HANDLE, [pointer, wt.LPCWSTR]),
                "SetInformationJobObject": (
                    wt.BOOL,
                    [wt.HANDLE, ct.c_int, pointer, wt.DWORD],
                ),
                "AssignProcessToJobObject": (wt.BOOL, [wt.HANDLE, wt.HANDLE]),
                "TerminateJobObject": (wt.BOOL, [wt.HANDLE, wt.UINT]),
                "TerminateProcess": (wt.BOOL, [wt.HANDLE, wt.UINT]),
                "ResumeThread": (wt.DWORD, [wt.HANDLE]),
                "OpenThread": (wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]),
                "CancelSynchronousIo": (wt.BOOL, [wt.HANDLE]),
                "WaitForSingleObject": (wt.DWORD, [wt.HANDLE, wt.DWORD]),
                "GetExitCodeProcess": (wt.BOOL, [wt.HANDLE, ct.POINTER(wt.DWORD)]),
                "ReadFile": (
                    wt.BOOL,
                    [wt.HANDLE, pointer, wt.DWORD, ct.POINTER(wt.DWORD), pointer],
                ),
                "WriteFile": (
                    wt.BOOL,
                    [wt.HANDLE, pointer, wt.DWORD, ct.POINTER(wt.DWORD), pointer],
                ),
                "PeekNamedPipe": (
                    wt.BOOL,
                    [
                        wt.HANDLE,
                        pointer,
                        wt.DWORD,
                        pointer,
                        ct.POINTER(wt.DWORD),
                        pointer,
                    ],
                ),
                "GetConsoleMode": (wt.BOOL, [wt.HANDLE, ct.POINTER(wt.DWORD)]),
                "GetConsoleCursorInfo": (wt.BOOL, [wt.HANDLE, ct.POINTER(_CursorInfo)]),
            }
            for name, (result, arguments) in signatures.items():
                function = getattr(
                    self.dll, name
                )  # Missing ConPTY is a failure, not a skip.
                function.restype, function.argtypes = result, arguments
                setattr(self, name, function)

        @staticmethod
        def check(result):
            if not result:
                raise ct.WinError(ct.get_last_error())
            return result

        @staticmethod
        def hresult(result):
            assert result >= 0, f"ConPTY HRESULT 0x{result & 0xFFFFFFFF:08x}"

    class _WindowsProcess:
        def __init__(self, api, handle):
            self.api, self.handle = api, handle

        def poll(self):
            status = self.api.WaitForSingleObject(self.handle, 0)
            if status == 258:  # WAIT_TIMEOUT; 259 is also a possible real exit code.
                return None
            assert status == 0, "failed waiting for ConPTY child"
            result = wt.DWORD()
            self.api.check(self.api.GetExitCodeProcess(self.handle, ct.byref(result)))
            return result.value

    class _WindowsTerminal(Terminal):
        """Real ConPTY, suspended wrapper, and kill-on-close owned process tree.

        The independent bounded reader stays active during ClosePseudoConsole;
        otherwise its final frame can deadlock cleanup. The private receipt is
        written inside the child console and contains only modes/cursor/exit.
        """

        def __init__(
            self,
            origin,
            token,
            *args,
            columns=120,
            rows=40,
            extra_env=None,
            redirect=None,
            light_background=False,
        ):
            self.api = api = _WindowsAPI()
            self._handles = []
            self._console = wt.HANDLE()
            self._attributes = None
            self._reader = None
            self._writer = None
            self._stop = Event()
            self._chunks = Queue(maxsize=64)
            self._reader_error = None
            self._temporary = tempfile.TemporaryDirectory(prefix="workstream-conpty-")
            self._receipt = Path(self._temporary.name) / "modes.json"
            self.process = None
            self._screen_setup(columns, rows, light_background)
            try:
                input_read, self._input = self._pipe()
                self._output, output_write = self._pipe()
                api.hresult(
                    api.CreatePseudoConsole(
                        _Coord(columns, rows),
                        input_read,
                        output_write,
                        0,
                        ct.byref(self._console),
                    )
                )
                self._reader = Thread(target=self._drain, daemon=True)
                self._reader.start()
                size = ct.c_size_t()
                api.InitializeProcThreadAttributeList(None, 1, 0, ct.byref(size))
                assert size.value, "missing ConPTY attribute-list size"
                attributes = ct.create_string_buffer(size.value)
                api.check(
                    api.InitializeProcThreadAttributeList(
                        attributes, 1, 0, ct.byref(size)
                    )
                )
                self._attributes = attributes
                # This attribute takes HPCON itself, not a pointer to HPCON.
                api.check(
                    api.UpdateProcThreadAttribute(
                        attributes,
                        0,
                        0x00020016,
                        self._console,
                        ct.sizeof(wt.HANDLE),
                        None,
                        None,
                    )
                )
                startup = _StartupInfoEx()
                startup.StartupInfo.cb = ct.sizeof(startup)
                startup.lpAttributeList = ct.cast(attributes, ct.c_void_p)
                info = _ProcessInfo()
                argv = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--conpty-child",
                    str(self._receipt),
                    redirect or "none",
                    executable(),
                    "tui",
                    *args,
                ]
                command = ct.create_unicode_buffer(subprocess.list2cmdline(argv))
                env = environment(origin, token, extra_env)
                env_block = ct.create_unicode_buffer(
                    "\0".join(
                        f"{key}={value}"
                        for key, value in sorted(
                            env.items(), key=lambda item: item[0].upper()
                        )
                    )
                    + "\0"
                )
                self._job = api.check(api.CreateJobObjectW(None, None))
                self._handles.append(self._job)
                limits = _JobLimits()
                limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
                api.check(
                    api.SetInformationJobObject(
                        self._job, 9, ct.byref(limits), ct.sizeof(limits)
                    )
                )
                api.check(
                    api.CreateProcessW(
                        sys.executable,
                        command,
                        None,
                        None,
                        False,
                        0x00080000
                        | 0x00000400
                        | 0x00000004,  # extended/unicode/suspended
                        env_block,
                        None,
                        ct.byref(startup),
                        ct.byref(info),
                    )
                )
                self._handles.extend([info.hProcess, info.hThread])
                self.process = _WindowsProcess(api, info.hProcess)
                # The wrapper cannot spawn the CLI before it belongs to our job.
                api.check(api.AssignProcessToJobObject(self._job, info.hProcess))
                assert api.ResumeThread(info.hThread) != 0xFFFFFFFF, (
                    "cannot resume ConPTY child"
                )
                self._close_handle(info.hThread)
                self._close_handle(input_read)
                self._close_handle(output_write)
                api.DeleteProcThreadAttributeList(attributes)
                self._attributes = None
            except BaseException:
                self.close()
                raise

        def _pipe(self):
            first, second = wt.HANDLE(), wt.HANDLE()
            self.api.check(
                self.api.CreatePipe(ct.byref(first), ct.byref(second), None, 0)
            )
            self._handles.extend([first.value, second.value])
            return first.value, second.value

        def _close_handle(self, handle):
            self.api.check(self.api.CloseHandle(handle))
            self._handles.remove(handle)

        def _drain(self):
            try:
                while not self._stop.is_set():
                    available = wt.DWORD()
                    if not self.api.PeekNamedPipe(
                        self._output, None, 0, None, ct.byref(available), None
                    ):
                        if ct.get_last_error() in {
                            109,
                            232,
                        }:  # broken/disconnected pipe
                            return
                        raise ct.WinError(ct.get_last_error())
                    if not available.value:
                        self._stop.wait(0.005)
                        continue
                    buffer = ct.create_string_buffer(min(65536, available.value))
                    count = wt.DWORD()
                    self.api.check(
                        self.api.ReadFile(
                            self._output, buffer, len(buffer), ct.byref(count), None
                        )
                    )
                    try:
                        self._chunks.put_nowait(buffer.raw[: count.value])
                    except Full:
                        self._reader_error = "unbounded ConPTY output"
                        # Keep draining even on failure so teardown cannot deadlock.
            except Exception as error:
                self._reader_error = f"ConPTY reader failed: {type(error).__name__}"

        def _write(self, data):
            assert len(data) <= 4096, "unbounded ConPTY input"
            errors = []

            def write():
                try:
                    count = wt.DWORD()
                    self.api.check(
                        self.api.WriteFile(
                            self._input,
                            data,
                            len(data),
                            ct.byref(count),
                            None,
                        )
                    )
                    assert count.value == len(data), "short ConPTY input write"
                except Exception as error:
                    errors.append(error)

            # A stalled child must not block the test thread inside WriteFile.
            self._writer = Thread(target=write, daemon=True)
            self._writer.start()
            self._writer.join(timeout=2)
            if self._writer.is_alive():
                handle = self.api.check(
                    self.api.OpenThread(0x0001, False, self._writer.native_id)
                )
                try:
                    self.api.CancelSynchronousIo(handle)
                    self._writer.join(timeout=2)
                finally:
                    self.api.check(self.api.CloseHandle(handle))
                raise AssertionError("ConPTY input write timed out")
            if errors:
                raise errors[0]
            self._writer = None

        def pump(self, seconds=0.1):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                assert self._reader_error is None, self._reader_error
                try:
                    data = self._chunks.get(timeout=max(0, deadline - time.monotonic()))
                except Empty:
                    break
                self.raw.extend(data)
                assert len(self.raw) < 4 * 1024 * 1024, "unbounded terminal output"
                self._render(self.decoder.decode(data))

        def resize(self, columns, rows, *, notify=True):
            self.api.hresult(
                self.api.ResizePseudoConsole(self._console, _Coord(columns, rows))
            )
            self.columns, self.rows = columns, rows
            self.cells = [[" "] * columns for _ in range(rows)]
            self.x = self.y = 0
            self.scroll_top, self.scroll_bottom = 0, rows - 1

        def _assert_restored(self):
            assert self._receipt.stat().st_size < 4096, "unbounded mode receipt"
            receipt = json.loads(self._receipt.read_text(encoding="utf-8"))
            assert set(receipt) == {"before", "after", "exit"}, (
                "missing child console proof"
            )
            assert receipt["before"] == receipt["after"], (
                "child console modes/cursor not restored"
            )
            assert receipt["exit"] == self.process.poll(), "wrapper/CLI exit mismatch"
            self._assert_cursor_and_screen_restored()

        def assert_no_terminal_controls(self):
            # ConPTY synthesizes VT framing even for plain error text. Verify
            # actual child modes above and reject application alternate-screen
            # entry, rather than mistaking the host's framing for CLI output.
            assert b"\x1b[?1049h" not in self.raw

        def close(self):
            errors = []
            if self.process is not None:
                if self.process.poll() is None:
                    # Also terminates an unassigned suspended wrapper if job
                    # assignment failed; job closure owns all descendants.
                    self.api.TerminateProcess(self.process.handle, 1)
                self.api.TerminateJobObject(self._job, 1)
                if self.api.WaitForSingleObject(self.process.handle, 5000) != 0:
                    errors.append("ConPTY child did not terminate")
            if self._attributes is not None:
                self.api.DeleteProcThreadAttributeList(self._attributes)
                self._attributes = None
            if self._console.value:
                closer = Thread(
                    target=self.api.ClosePseudoConsole,
                    args=(self._console,),
                    daemon=True,
                )
                closer.start()
                closer.join(timeout=5)
                if closer.is_alive():
                    errors.append("ClosePseudoConsole timed out")
                self._console = wt.HANDLE()
            self._stop.set()
            if self._writer is not None:
                self._writer.join(timeout=5)
                if self._writer.is_alive():
                    errors.append("ConPTY writer did not terminate")
            if self._reader is not None:
                self._reader.join(timeout=5)
                if self._reader.is_alive():
                    errors.append("ConPTY reader did not terminate")
            for handle in reversed(self._handles):
                if not self.api.CloseHandle(handle):
                    errors.append("ConPTY handle did not close")
            self._handles.clear()
            self._temporary.cleanup()
            assert not errors, errors

    Terminal = _WindowsTerminal


def _conpty_child(receipt_path, redirect, argv):
    """Test-only wrapper: inspect this console, not the parent's pipe handles."""
    import msvcrt

    api = _WindowsAPI()
    input_fd = os.open("CONIN$", os.O_RDWR | os.O_BINARY)
    output_fd = os.open("CONOUT$", os.O_RDWR | os.O_BINARY)

    def snapshot():
        modes = []
        for fd in (input_fd, output_fd):
            mode = wt.DWORD()
            api.check(api.GetConsoleMode(msvcrt.get_osfhandle(fd), ct.byref(mode)))
            modes.append(mode.value)
        cursor = _CursorInfo()
        api.check(
            api.GetConsoleCursorInfo(msvcrt.get_osfhandle(output_fd), ct.byref(cursor))
        )
        return {"modes": modes, "cursor": [cursor.dwSize, bool(cursor.bVisible)]}

    try:
        before = snapshot()
        result = subprocess.run(  # noqa: S603 - fixed test binary/argv, no shell
            argv,
            stdin=subprocess.DEVNULL if redirect == "input" else input_fd,
            stdout=subprocess.DEVNULL if redirect == "output" else output_fd,
            stderr=output_fd,
            timeout=60,
            check=False,
        )
        receipt = {"before": before, "after": snapshot(), "exit": result.returncode}
        Path(receipt_path).write_text(json.dumps(receipt), encoding="utf-8")
        return result.returncode
    finally:
        os.close(input_fd)
        os.close(output_fd)


@contextmanager
def socket_peer(respond, *, capture_post=None):
    """Threaded hostile HTTP peer: every unexpected request is recorded/fails.

    The optional hook observes the exact POST headers and bytes before the
    ordinary three-argument responder runs. Existing GET-only peers stay strict.
    """
    requests = []
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - HTTP handler interface
            request = (self.command, self.path, self.headers.get("Authorization"))
            requests.append(request)
            try:
                if self.command == "POST" and capture_post is not None:
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    capture_post(self.path, dict(self.headers), body)
                result = respond(*request)
                status, body = result[:2]
                media_type = result[2] if len(result) == 3 else "application/json"
            except Exception as error:  # fixture errors must reach the test thread
                failures.append(error)
                status, body, media_type = 500, {"unexpected": True}, "application/json"
            encoded = (
                body
                if isinstance(body, bytes)
                else json.dumps(body, ensure_ascii=False).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass  # cancellation closes the connection, not the test response

        do_POST = do_GET
        do_PUT = do_GET
        do_PATCH = do_GET
        do_DELETE = do_GET

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
        assert not failures, failures
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    assert os.name == "nt" and sys.argv[1] == "--conpty-child"
    raise SystemExit(_conpty_child(sys.argv[2], sys.argv[3], sys.argv[4:]))
