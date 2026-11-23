"""Bound the native CLI startup read used by browser qualification."""
from concurrent.futures import ThreadPoolExecutor
import subprocess


def login_line(command: subprocess.Popen, timeout: float = 20) -> str:
    """Reap a stalled CLI before waiting for its stderr reader to shut down."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            return executor.submit(command.stderr.readline).result(timeout=timeout)
        except TimeoutError:
            command.kill()
            command.wait(timeout=10)
            raise
