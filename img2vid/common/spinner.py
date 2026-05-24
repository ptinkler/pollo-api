import sys
import threading
import time


class Spinner:
    def __init__(self, message="Processing", delay=0.1, spinner_chars=None):
        self.message = message
        self.delay = delay
        self.spinner_chars = spinner_chars or ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.running = False
        self._thread = None
        self._idx = 0
        self._start_time = None
        self._elapsed = 0

    def start(self):
        self.running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self):
        while self.running:
            self._elapsed = time.time() - self._start_time if self._start_time else 0
            sys.stdout.write(f"\r{self.spinner_chars[self._idx % len(self.spinner_chars)]} {self.message}... {self._elapsed:.1f}s")
            sys.stdout.flush()
            self._idx += 1
            time.sleep(self.delay)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join()
        sys.stdout.write("\r   \r")  # Clear spinner line
        sys.stdout.flush()
        print(f"Total time: {self._elapsed:.1f}s")
