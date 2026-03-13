"""Tests for core.ibt_parser — TelemetryData, load_demo_data, _parse_session_yaml."""
import numpy as np
import pytest

from core.ibt_parser import IBTParser, TelemetryData, load_demo_data


# ── TelemetryData basics ────────────────────────────────────────────

class TestTelemetryData:
    def test_defaults(self):
        td = TelemetryData()
        assert td.car_name == ""
        assert td.track_name == ""
        assert td.num_laps == 0
        assert td.lap_times == []
        assert td.lap_boundaries == []
        assert td.tick_rate == 60

    def test_get_set_channel(self):
        td = TelemetryData()
        arr = np.array([1.0, 2.0, 3.0])
        td.set_channel("Speed", arr)
        np.testing.assert_array_equal(td.get_channel("Speed"), arr)

    def test_get_missing_channel_returns_none(self):
        td = TelemetryData()
        result = td.get_channel("NonExistent")
        assert result is None

    def test_channel_names(self):
        td = TelemetryData()
        td.set_channel("Alpha", np.array([1]))
        td.set_channel("Beta", np.array([2]))
        assert set(td.channel_names) == {"Alpha", "Beta"}


# ── load_demo_data ──────────────────────────────────────────────────

class TestLoadDemoData:
    def test_returns_telemetry_data(self, demo_data):
        assert isinstance(demo_data, TelemetryData)

    def test_car_and_track(self, demo_data):
        assert "ferrari" in demo_data.car_name.lower() or "296" in demo_data.car_name
        assert "Sebring" in demo_data.track_name

    def test_has_8_laps(self, demo_data):
        assert demo_data.num_laps == 8
        assert len(demo_data.lap_times) == 8

    def test_lap_times_reasonable(self, demo_data):
        for lt in demo_data.lap_times:
            assert 85 < lt < 100, f"Unexpected lap time {lt}"

    def test_essential_channels_present(self, demo_data):
        for ch in ("Speed", "Throttle", "Brake", "SteeringWheelAngle",
                    "RPM", "FuelLevel", "Gear", "LapDistPct"):
            assert len(demo_data.get_channel(ch)) > 0, f"Missing channel {ch}"

    def test_tire_channels_present(self, demo_data):
        for corner in ("LF", "RF", "LR", "RR"):
            assert len(demo_data.get_channel(f"{corner}tempCM")) > 0
            assert len(demo_data.get_channel(f"{corner}press")) > 0

    def test_tick_rate(self, demo_data):
        assert demo_data.tick_rate == 60


# ── IBTParser edge cases ────────────────────────────────────────────

class TestIBTParser:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            IBTParser(str(tmp_path / "nonexistent.ibt"))

    def test_parse_session_yaml_empty(self):
        parser = IBTParser.__new__(IBTParser)
        result = parser._parse_session_yaml("")
        assert isinstance(result, dict)

    def test_parse_session_yaml_extracts_car(self):
        parser = IBTParser.__new__(IBTParser)
        yaml_text = 'DriverCarTPath: vehicles/gt3/ferrari_296_gt3\n'
        result = parser._parse_session_yaml(yaml_text)
        assert "ferrari_296_gt3" in result.get("car_name", "")

    def test_parse_session_yaml_extracts_track(self):
        parser = IBTParser.__new__(IBTParser)
        yaml_text = 'TrackDisplayName: Daytona International Speedway\n'
        result = parser._parse_session_yaml(yaml_text)
        assert result.get("track_name") == "Daytona International Speedway"

    def test_parse_session_yaml_bad_values_no_crash(self):
        parser = IBTParser.__new__(IBTParser)
        yaml_text = 'AirTemp: not_a_number\nTrackTemp: also_bad\n'
        result = parser._parse_session_yaml(yaml_text)
        # Should not raise; bad floats are silently skipped
        assert isinstance(result, dict)


# ── LapDistPct fallback ─────────────────────────────────────────────

class TestLapFallback:
    def test_fallback_with_lap_current_time(self):
        """When LapDistPct is missing, _derive_laps_fallback uses LapCurrentLapTime."""
        data = TelemetryData(tick_rate=60)
        total = 3 * 5400  # 3 laps at 90s, 60 Hz
        session_time = np.linspace(0, 270, total)
        # Simulate LapCurrentLapTime resetting each lap
        lap_cur = np.concatenate([
            np.linspace(0, 89.9, 5400),
            np.linspace(0, 89.9, 5400),
            np.linspace(0, 89.9, 5400),
        ])
        data.set_channel('SessionTime', session_time)
        data.set_channel('LapCurrentLapTime', lap_cur)

        parser = IBTParser.__new__(IBTParser)
        parser._derive_laps_fallback(data)
        assert data.num_laps >= 2

    def test_fallback_with_session_time_only(self):
        """When both LapDistPct and LapCurrentLapTime are missing, use fixed splits."""
        data = TelemetryData(tick_rate=60)
        total = 5 * 5400
        session_time = np.linspace(0, 450, total)
        data.set_channel('SessionTime', session_time)

        parser = IBTParser.__new__(IBTParser)
        parser._derive_laps_fallback(data)
        assert data.num_laps >= 3

    def test_fallback_no_channels_does_nothing(self):
        """With no channels at all, fallback silently does nothing."""
        data = TelemetryData()
        parser = IBTParser.__new__(IBTParser)
        parser._derive_laps_fallback(data)
        assert data.num_laps == 0
