"""Tests for IBT parser edge cases — truncated, corrupt, empty files."""
import struct
import numpy as np
import pytest
from core.ibt_parser import IBTParser, TelemetryData, load_demo_data


class TestMalformedIBT:
    """Edge cases for binary IBT parsing."""

    def test_file_too_small_raises(self, tmp_path):
        """Files smaller than 112 bytes should be rejected."""
        f = tmp_path / "tiny.ibt"
        f.write_bytes(b"\x00" * 50)
        with pytest.raises(ValueError, match="too small"):
            IBTParser(str(f)).parse()

    def test_empty_file_raises(self, tmp_path):
        """Zero-length file should be rejected."""
        f = tmp_path / "empty.ibt"
        f.write_bytes(b"")
        with pytest.raises(ValueError):
            IBTParser(str(f)).parse()

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            IBTParser("nonexistent_file_12345.ibt").parse()

    def test_oversized_file_raises(self, tmp_path):
        """Files over 500 MB should be rejected."""
        f = tmp_path / "huge.ibt"
        f.write_bytes(b"\x00" * 112)
        # Monkey-patch os.path.getsize
        import os
        real_getsize = os.path.getsize
        os.path.getsize = lambda _: 600 * 1024 * 1024
        try:
            with pytest.raises(ValueError, match="500 MB"):
                IBTParser(str(f)).parse()
        finally:
            os.path.getsize = real_getsize

    def test_negative_var_count_raises(self, tmp_path):
        """Negative num_vars in header should be rejected."""
        header = bytearray(200)
        struct.pack_into('i', header, 0, 1)     # version
        struct.pack_into('i', header, 8, 60)    # tick_rate
        struct.pack_into('i', header, 12, 0)    # session_info_offset
        struct.pack_into('i', header, 16, 0)    # session_info_len
        struct.pack_into('i', header, 20, -5)   # num_vars (negative)
        struct.pack_into('i', header, 24, 112)  # var_header_offset
        struct.pack_into('i', header, 28, 1)    # num_buf
        struct.pack_into('i', header, 32, 4)    # buf_len
        f = tmp_path / "neg_vars.ibt"
        f.write_bytes(bytes(header))
        with pytest.raises(ValueError, match="Suspicious"):
            IBTParser(str(f)).parse()

    def test_excessive_var_count_raises(self, tmp_path):
        """num_vars > 10000 should be rejected as suspicious."""
        header = bytearray(200)
        struct.pack_into('i', header, 0, 1)
        struct.pack_into('i', header, 8, 60)
        struct.pack_into('i', header, 12, 0)
        struct.pack_into('i', header, 16, 0)
        struct.pack_into('i', header, 20, 50000)  # too many
        struct.pack_into('i', header, 24, 112)
        struct.pack_into('i', header, 28, 1)
        struct.pack_into('i', header, 32, 4)
        f = tmp_path / "many_vars.ibt"
        f.write_bytes(bytes(header))
        with pytest.raises(ValueError, match="Suspicious"):
            IBTParser(str(f)).parse()

    def test_truncated_var_headers(self, tmp_path):
        """File truncated in the middle of variable headers should not crash."""
        header = bytearray(200)
        struct.pack_into('i', header, 0, 1)
        struct.pack_into('i', header, 8, 60)
        struct.pack_into('i', header, 12, 0)
        struct.pack_into('i', header, 16, 0)
        struct.pack_into('i', header, 20, 10)    # claims 10 vars
        struct.pack_into('i', header, 24, 112)   # var_header starts at 112
        struct.pack_into('i', header, 28, 0)     # no data buffers
        struct.pack_into('i', header, 32, 4)
        f = tmp_path / "truncated.ibt"
        f.write_bytes(bytes(header))
        # Should parse successfully with 0 variables (truncated)
        data = IBTParser(str(f)).parse()
        assert isinstance(data, TelemetryData)
        assert data.num_laps == 0


class TestDemoData:
    """Verify demo data generator produces valid output."""

    def test_demo_data_channels(self):
        d = load_demo_data()
        assert d.num_laps == 8
        assert d.get_channel('Speed') is not None
        assert d.get_channel('Throttle') is not None
        assert d.get_channel('Brake') is not None
        assert d.get_channel('LapDistPct') is not None

    def test_demo_data_boundaries(self):
        d = load_demo_data()
        assert len(d.lap_boundaries) == d.num_laps + 1
        assert d.lap_boundaries[0] == 0

    def test_demo_data_lap_times_positive(self):
        d = load_demo_data()
        assert all(t > 0 for t in d.lap_times)


class TestLapResetThreshold:
    """Test the LAP_RESET_THRESHOLD class attribute."""

    def test_threshold_is_accessible(self):
        assert hasattr(IBTParser, 'LAP_RESET_THRESHOLD')
        assert IBTParser.LAP_RESET_THRESHOLD == 0.5
