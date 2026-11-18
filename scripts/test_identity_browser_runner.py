"""Actual child-process proof of the browser runner's bounded startup."""
import subprocess
import sys
import time
import unittest

from scripts.identity_browser_runner import login_line


class BrowserRunnerTests(unittest.TestCase):
    def test_partial_line_stall_is_reaped_before_executor_shutdown(self):
        child = subprocess.Popen([sys.executable, "-c",
            "import sys,time;sys.stderr.write('partial');sys.stderr.flush();time.sleep(4)"],
            stderr=subprocess.PIPE, text=True)
        try:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                login_line(child, timeout=0.1)
            self.assertLess(time.monotonic() - start, 2)
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            child.stderr.close()

    def test_complete_line_is_returned(self):
        child = subprocess.Popen([sys.executable, "-c",
            "import sys;print('Sign in using your browser: https://example.test',file=sys.stderr)"],
            stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(login_line(child), "Sign in using your browser: https://example.test\n")
        finally:
            child.wait(timeout=5)
            child.stderr.close()
