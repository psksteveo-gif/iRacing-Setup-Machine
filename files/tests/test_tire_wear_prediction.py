"""Tests for core.tire_wear_prediction — Tire Wear Projection Model."""
import numpy as np
import pytest

from core.tire_wear_prediction import (
    predict_tire_wear, TireWearPrediction, _compute_wear_pct,
    MIN_LAPS_FOR_PREDICTION, PROJECTION_LAPS,
)
from core.advanced_analysis import TireDegReport, StintAnalyzer


# ── Basic prediction ──────────────────────────────────────────────

class TestPredictTireWear:
    def test_returns_prediction(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert isinstance(p, TireWearPrediction)

    def test_actual_laps_match(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert p.actual_laps == list(range(1, len(r.lap_times) + 1))
        assert p.actual_times == list(r.lap_times)

    def test_projected_laps_generated(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert len(p.projected_laps) == PROJECTION_LAPS
        assert p.projected_laps[0] == len(r.lap_times) + 1

    def test_confidence_bands_widen(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        if len(p.confidence_upper) >= 2:
            band_first = p.confidence_upper[0] - p.confidence_lower[0]
            band_last = p.confidence_upper[-1] - p.confidence_lower[-1]
            assert band_last >= band_first

    def test_grip_cliff_positive(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert p.grip_cliff_lap > 0

    def test_pit_window_valid(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert p.pit_window_open >= 1
        assert p.pit_window_close >= p.pit_window_open

    def test_fit_type_set(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert p.fit_type in ("linear", "quadratic")

    def test_r_squared_in_range(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert -1.0 <= p.r_squared <= 1.0

    def test_has_findings(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert len(p.findings) >= 1

    def test_tire_life_in_range(self, demo_data):
        r = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(r)
        assert 0.0 <= p.tire_life_pct <= 100.0


# ── Edge cases ────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_lap_times(self):
        r = TireDegReport()
        p = predict_tire_wear(r)
        assert p.fit_type == "none"
        assert "Not enough" in p.findings[0]

    def test_single_lap(self):
        r = TireDegReport(lap_times=[90.0])
        p = predict_tire_wear(r)
        assert p.fit_type == "none"

    def test_two_laps(self):
        r = TireDegReport(lap_times=[90.0, 90.5])
        p = predict_tire_wear(r)
        assert "clean laps" in p.findings[0]  # < MIN_LAPS_FOR_PREDICTION

    def test_identical_times_no_crash(self):
        r = TireDegReport(lap_times=[90.0] * 8)
        p = predict_tire_wear(r)
        assert isinstance(p, TireWearPrediction)
        assert p.grip_cliff_lap > 0

    def test_outlier_removed(self):
        """Outlier lap (e.g. pit/safety car) should be excluded from fit."""
        times = [90.0, 90.2, 90.4, 90.6, 200.0, 90.8, 91.0, 91.2]
        r = TireDegReport(lap_times=times)
        p = predict_tire_wear(r)
        # The fit should not be distorted by the 200s outlier
        assert p.fit_type in ("linear", "quadratic")
        for t in p.projected_times:
            assert t < 150.0  # should be reasonable, not pulled toward 200

    def test_custom_projection_length(self):
        r = TireDegReport(lap_times=[90 + i * 0.1 for i in range(10)])
        p = predict_tire_wear(r, projection_laps=5)
        assert len(p.projected_laps) == 5


# ── Wear percentage from temp progression ──────────────────────────

class TestWearPercentage:
    def test_wear_from_temps(self):
        r = TireDegReport(
            lap_times=[90 + i * 0.05 for i in range(6)],
            tire_temp_progression={
                'LF': [85, 87, 89, 91, 93, 95],
                'RF': [85, 87, 89, 91, 93, 95],
                'LR': [85, 86, 87, 88, 89, 90],
                'RR': [85, 86, 87, 88, 89, 90],
            }
        )
        p = predict_tire_wear(r)
        assert len(p.wear_pct_per_lap) == 6
        assert p.wear_pct_per_lap[0] == 0.0  # baseline
        assert p.wear_pct_per_lap[-1] > 0.0  # wear accumulated

    def test_wear_monotonic(self):
        # Temps rising steadily → wear should be monotonically increasing
        r = TireDegReport(
            lap_times=[90 + i * 0.1 for i in range(8)],
            tire_temp_progression={
                'LF': [80 + i * 2 for i in range(8)],
                'RF': [80 + i * 2 for i in range(8)],
                'LR': [80 + i * 1.5 for i in range(8)],
                'RR': [80 + i * 1.5 for i in range(8)],
            }
        )
        p = predict_tire_wear(r)
        for i in range(1, len(p.wear_pct_per_lap)):
            assert p.wear_pct_per_lap[i] >= p.wear_pct_per_lap[i - 1]

    def test_peak_wear_corner_identified(self):
        r = TireDegReport(
            lap_times=[90, 90.1, 90.2, 90.3, 90.4],
            tire_temp_progression={
                'LF': [80, 82, 84, 86, 88],  # +8
                'RF': [80, 85, 90, 95, 100],  # +20 — hottest
                'LR': [80, 81, 82, 83, 84],
                'RR': [80, 81, 82, 83, 84],
            }
        )
        p = predict_tire_wear(r)
        assert p.peak_wear_corner == 'RF'

    def test_no_temps_no_crash(self):
        r = TireDegReport(lap_times=[90, 90.1, 90.2, 90.3, 90.4])
        p = predict_tire_wear(r)
        assert p.wear_pct_per_lap == []
        assert p.tire_life_pct == 100.0


# ── Integration with demo data ────────────────────────────────────

class TestDemoIntegration:
    def test_full_pipeline(self, demo_data):
        """End-to-end: parse demo → stint analysis → tire wear prediction."""
        stint = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(stint)
        # Should have actual + projected data
        assert len(p.actual_laps) >= 5
        assert len(p.projected_laps) == PROJECTION_LAPS
        assert p.grip_cliff_lap > 0
        assert p.pit_window_open >= 1
        assert len(p.findings) >= 1

    def test_wear_pct_from_demo(self, demo_data):
        """Demo data has tire temp channels so wear % should be computed."""
        stint = StintAnalyzer().analyze(demo_data)
        p = predict_tire_wear(stint)
        # Demo data generates temp progression
        if stint.tire_temp_progression:
            assert len(p.wear_pct_per_lap) > 0
