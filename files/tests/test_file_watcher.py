"""Tests for file watcher."""
import os
import tempfile
import time
import pytest
from core.file_watcher import FileWatcher


class TestFileWatcher:
    def test_init(self, tmp_path):
        watcher = FileWatcher(
            telemetry_dir=str(tmp_path / "telemetry"),
            setups_dir=str(tmp_path / "setups"),
        )
        assert not watcher.is_running

    def test_start_stop(self, tmp_path):
        tdir = tmp_path / "telemetry"
        tdir.mkdir()
        sdir = tmp_path / "setups"
        sdir.mkdir()
        watcher = FileWatcher(
            telemetry_dir=str(tdir), setups_dir=str(sdir),
            poll_interval=0.1,
        )
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_detects_new_ibt_file(self, tmp_path):
        tdir = tmp_path / "telemetry"
        tdir.mkdir()
        detected = []

        watcher = FileWatcher(
            telemetry_dir=str(tdir),
            setups_dir=str(tmp_path / "setups"),
            on_new_telemetry=lambda f: detected.append(f),
            poll_interval=0.2,
        )
        watcher.start()
        try:
            # Create a new .ibt file after watcher started
            new_file = tdir / "test_session.ibt"
            new_file.write_bytes(b'\x00' * 100)
            # Wait for detection (poll + stability check)
            time.sleep(1.5)
        finally:
            watcher.stop()

        assert len(detected) == 1
        assert "test_session.ibt" in detected[0]

    def test_ignores_existing_files(self, tmp_path):
        tdir = tmp_path / "telemetry"
        tdir.mkdir()
        # Create file BEFORE watcher starts
        existing = tdir / "old.ibt"
        existing.write_bytes(b'\x00' * 50)

        detected = []
        watcher = FileWatcher(
            telemetry_dir=str(tdir),
            setups_dir=str(tmp_path / "s"),
            on_new_telemetry=lambda f: detected.append(f),
            poll_interval=0.2,
        )
        watcher.start()
        time.sleep(1.0)
        watcher.stop()
        assert len(detected) == 0

    def test_missing_directory(self, tmp_path):
        # Should not crash with missing dirs
        watcher = FileWatcher(
            telemetry_dir=str(tmp_path / "nonexistent"),
            setups_dir=str(tmp_path / "also_nonexistent"),
            poll_interval=0.1,
        )
        watcher.start()
        time.sleep(0.5)
        watcher.stop()
        assert True  # Did not crash

    def test_scan_dir_static(self, tmp_path):
        tdir = tmp_path / "t"
        tdir.mkdir()
        (tdir / "a.ibt").write_bytes(b'\x00')
        (tdir / "b.txt").write_bytes(b'\x00')
        result = FileWatcher._scan_dir(str(tdir), {'.ibt'})
        assert len(result) == 1
