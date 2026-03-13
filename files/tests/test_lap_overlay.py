"""Tests for lap overlay comparison."""
import pytest
import numpy as np
from core.lap_overlay import extract_lap_trace, compare_laps, LapTrace, LapComparison, RESAMPLE_POINTS


class TestExtractLapTrace:
    def test_basic_extraction(self, demo_data):
        trace = extract_lap_trace(demo_data, 0)
        assert trace is not None
        assert trace.lap_idx == 0
        assert len(trace.dist_pct) == RESAMPLE_POINTS
        assert len(trace.speed) == RESAMPLE_POINTS
        assert len(trace.throttle) == RESAMPLE_POINTS
        assert len(trace.brake) == RESAMPLE_POINTS
        assert trace.dist_pct[0] == pytest.approx(0.0, abs=0.01)
        assert trace.dist_pct[-1] == pytest.approx(1.0, abs=0.01)

    def test_all_laps_extractable(self, demo_data):
        for i in range(demo_data.num_laps):
            trace = extract_lap_trace(demo_data, i)
            assert trace is not None
            assert trace.lap_idx == i

    def test_invalid_lap_returns_none(self, demo_data):
        assert extract_lap_trace(demo_data, -1) is None
        assert extract_lap_trace(demo_data, 999) is None

    def test_lap_time_populated(self, demo_data):
        trace = extract_lap_trace(demo_data, 0)
        assert trace is not None
        assert trace.lap_time > 0

    def test_speed_range_realistic(self, demo_data):
        trace = extract_lap_trace(demo_data, 0)
        assert trace is not None
        assert np.min(trace.speed) >= 0
        assert np.max(trace.speed) < 200


class TestCompareLaps:
    def test_basic_comparison(self, demo_data):
        cmp = compare_laps(demo_data, 0, 1)
        assert cmp is not None
        assert len(cmp.speed_delta) == RESAMPLE_POINTS
        assert len(cmp.throttle_delta) == RESAMPLE_POINTS
        assert len(cmp.brake_delta) == RESAMPLE_POINTS

    def test_summary_stats(self, demo_data):
        cmp = compare_laps(demo_data, 0, 1)
        assert cmp is not None
        assert cmp.avg_speed_a > 0
        assert cmp.avg_speed_b > 0
        assert cmp.max_speed_a > cmp.avg_speed_a
        assert 0 <= cmp.throttle_pct_a <= 100
        assert 0 <= cmp.braking_pct_a <= 100

    def test_time_delta(self, demo_data):
        cmp = compare_laps(demo_data, 0, 1)
        assert cmp is not None
        expected = demo_data.lap_times[1] - demo_data.lap_times[0]
        assert cmp.time_delta == pytest.approx(expected, abs=0.01)

    def test_invalid_laps(self, demo_data):
        assert compare_laps(demo_data, -1, 0) is None
        assert compare_laps(demo_data, 0, 999) is None

    def test_zones_are_lists(self, demo_data):
        cmp = compare_laps(demo_data, 0, 1)
        assert cmp is not None
        assert isinstance(cmp.speed_gain_zones, list)
        assert isinstance(cmp.speed_loss_zones, list)

    def test_same_lap_comparison(self, demo_data):
        cmp = compare_laps(demo_data, 0, 0)
        assert cmp is not None
        assert cmp.time_delta == pytest.approx(0.0, abs=0.001)
        assert np.max(np.abs(cmp.speed_delta)) < 0.01
