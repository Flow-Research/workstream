"""Bounded SMTP capture for isolated provider tests; never a production mail service."""
from __future__ import annotations

import queue
from pathlib import Path
import time
import uuid
import socketserver
import threading


class Mailbox(socketserver.ThreadingTCPServer):
    """Bind only the owned Docker-network gateway and retain synthetic mail in memory."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, gateway: str, port: int = 0, messages=None):
        self.messages = messages if messages is not None else queue.Queue(maxsize=30)
        self.available = True
        self.rejected_data = 0
        super().__init__((gateway, port), _SMTP)
        self.worker = threading.Thread(target=self.serve_forever, daemon=True)
        self.worker.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.worker.join(timeout=5)


class _SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        self.wfile.write(b"220 fixture ESMTP\r\n")
        for _ in range(100):
            line = self.rfile.readline(8193)
            if not line or len(line) > 8192:
                return
            verb = line.split(b" ", 1)[0].strip().upper()
            if verb in (b"EHLO", b"HELO"):
                self.wfile.write(b"250 fixture\r\n")
            elif verb in (b"MAIL", b"RCPT", b"RSET", b"NOOP"):
                self.wfile.write(b"250 OK\r\n")
            elif verb == b"DATA":
                if not self.server.available or not getattr(self.server.messages, "available", True):
                    self.server.rejected_data += 1
                    if isinstance(self.server.messages, FileMessages):
                        (self.server.messages.directory / "rejected-data").touch(mode=0o600)
                    self.wfile.write(b"451 fixture temporarily unavailable\r\n")
                    continue
                self.wfile.write(b"354 Send message\r\n")
                message = bytearray()
                while len(message) <= 1024 * 1024:
                    part = self.rfile.readline(8193)
                    if part == b".\r\n":
                        break
                    if not part or len(part) > 8192:
                        return
                    message.extend(part[1:] if part.startswith(b"..") else part)
                else:
                    self.wfile.write(b"552 fixture size limit\r\n")
                    return
                self.server.messages.put_nowait(bytes(message))
                self.wfile.write(b"250 Stored\r\n")
            elif verb == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                return
            else:
                self.wfile.write(b"502 Unsupported\r\n")


class FileMessages:
    """Private fixture spool shared only with the owned SMTP container."""
    def __init__(self, directory):
        self.directory = Path(directory)

    @property
    def available(self):
        return not (self.directory / "unavailable").exists()

    def empty(self):
        return not any(self.directory.glob("*.eml"))

    def put_nowait(self, message):
        if len(list(self.directory.glob("*.eml"))) >= 30:
            raise queue.Full
        target = self.directory / (str(time.time_ns()) + "-" + uuid.uuid4().hex)
        target.write_bytes(message)
        target.rename(target.with_suffix(".eml"))

    def get(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages = sorted(self.directory.glob("*.eml"))
            if messages:
                value = messages[0].read_bytes()
                messages[0].unlink()
                return value
            time.sleep(0.1)
        raise queue.Empty


if __name__ == "__main__":
    import signal
    receiver = Mailbox("0.0.0.0", 1025, FileMessages("/mail"))
    signal.pause()
