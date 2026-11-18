"""Bounded SMTP capture for isolated provider tests; never a production mail service."""
from __future__ import annotations

import queue
import socketserver
import threading


class Mailbox(socketserver.ThreadingTCPServer):
    """Bind only the owned Docker-network gateway and retain synthetic mail in memory."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, gateway: str):
        self.messages = queue.Queue(maxsize=30)
        self.available = True
        super().__init__((gateway, 0), _SMTP)
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
                if not self.server.available:
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
