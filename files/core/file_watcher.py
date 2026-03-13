"""
Auto-Detect New Files — File watcher for iRacing telemetry and setup folders.
Uses polling (no external dependencies) to detect new .ibt and setup files.
"""

import os
import time
import threading
import logging
from typing import Callable, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)

# Default iRacing paths
DEFAULT_TELEMETRY_DIR = os.path.expanduser("~/Documents/iRacing/telemetry")
DEFAULT_SETUPS_DIR = os.path.expanduser("~/Documents/iRacing/setups")

POLL_INTERVAL_S = 3.0
IBT_EXTENSIONS = {'.ibt'}
SETUP_EXTENSIONS = {'.sto', '.json', '.htm'}


class FileWatcher:
    """
    Poll-based file watcher for iRacing directories.
    Detects new files and calls back when found.
    """

    def __init__(
        self,
        telemetry_dir: str = DEFAULT_TELEMETRY_DIR,
        setups_dir: str = DEFAULT_SETUPS_DIR,
        on_new_telemetry: Optional[Callable[[str], None]] = None,
        on_new_setup: Optional[Callable[[str], None]] = None,
        poll_interval: float = POLL_INTERVAL_S,
    ):
        self.telemetry_dir = telemetry_dir
        self.setups_dir = setups_dir
        self.on_new_telemetry = on_new_telemetry
        self.on_new_setup = on_new_setup
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._known_telemetry: Set[str] = set()
        self._known_setups: Set[str] = set()
        self._running = False

    def start(self):
        """Start watching directories in a background thread."""
        if self._running:
            return
        self._stop_event.clear()
        # Snapshot existing files on start (don't trigger for old files)
        self._known_telemetry = self._scan_dir(self.telemetry_dir, IBT_EXTENSIONS)
        self._known_setups = self._scan_setups(self.setups_dir)
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("FileWatcher started — telemetry: %s, setups: %s",
                     self.telemetry_dir, self.setups_dir)

    def stop(self):
        """Stop the file watcher."""
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("FileWatcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running and not self._stop_event.is_set()

    def _poll_loop(self):
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                self._check_telemetry()
                self._check_setups()
            except Exception:
                logger.exception("FileWatcher poll error")
            self._stop_event.wait(self.poll_interval)

    def _check_telemetry(self):
        if not os.path.isdir(self.telemetry_dir):
            return
        current = self._scan_dir(self.telemetry_dir, IBT_EXTENSIONS)
        new_files = current - self._known_telemetry
        for f in sorted(new_files):
            # Verify file is not still being written (size stable)
            if self._is_file_stable(f):
                logger.info("New telemetry file: %s", f)
                self._known_telemetry.add(f)
                if self.on_new_telemetry:
                    self.on_new_telemetry(f)
            # If not stable yet, leave it out—it'll be picked up next cycle

    def _check_setups(self):
        if not os.path.isdir(self.setups_dir):
            return
        current = self._scan_setups(self.setups_dir)
        new_files = current - self._known_setups
        for f in sorted(new_files):
            if self._is_file_stable(f):
                logger.info("New setup file: %s", f)
                self._known_setups.add(f)
                if self.on_new_setup:
                    self.on_new_setup(f)

    @staticmethod
    def _scan_dir(directory: str, extensions: Set[str]) -> Set[str]:
        """Recursively scan directory for files with given extensions."""
        found: Set[str] = set()
        if not os.path.isdir(directory):
            return found
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                if Path(fn).suffix.lower() in extensions:
                    found.add(os.path.join(root, fn))
        return found

    @staticmethod
    def _scan_setups(directory: str) -> Set[str]:
        """Scan setups directory for setup files."""
        found: Set[str] = set()
        if not os.path.isdir(directory):
            return found
        for root, _dirs, files in os.walk(directory):
            for fn in files:
                ext = Path(fn).suffix.lower()
                if ext in SETUP_EXTENSIONS:
                    found.add(os.path.join(root, fn))
        return found

    @staticmethod
    def _is_file_stable(path: str, wait: float = 0.5) -> bool:
        """Check if a file's size hasn't changed (not actively being written)."""
        try:
            size1 = os.path.getsize(path)
            time.sleep(wait)
            size2 = os.path.getsize(path)
            return size1 == size2 and size1 > 0
        except OSError:
            return False
