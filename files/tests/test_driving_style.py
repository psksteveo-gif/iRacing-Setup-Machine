"""Tests for core.driving_style — DrivingStyleAnalyzer."""
import pytest

from core.driving_style import DrivingStyleAnalyzer, DriverStyleReport


class TestDrivingStyleAnalyzer:
    def test_returns_report(self, demo_data):
        rpt = DrivingStyleAnalyzer().analyze(demo_data)
        assert isinstance(rpt, DriverStyleReport)

    def test_scores_in_range(self, demo_data):
        rpt = DrivingStyleAnalyzer().analyze(demo_data)
        for attr in ("brake_consistency", "throttle_smoothness",
                      "steering_smoothness", "trail_braking_score",
                      "oversteer_management", "overall_score"):
            score = getattr(rpt, attr)
            assert 0 <= score <= 100, f"{attr}={score} out of range"

    def test_has_findings(self, demo_data):
        rpt = DrivingStyleAnalyzer().analyze(demo_data)
        assert isinstance(rpt.findings, list)

    def test_has_style_profile(self, demo_data):
        rpt = DrivingStyleAnalyzer().analyze(demo_data)
        assert isinstance(rpt.style_profile, str)
        assert len(rpt.style_profile) > 0

    def test_full_throttle_pct_bounded(self, demo_data):
        rpt = DrivingStyleAnalyzer().analyze(demo_data)
        assert 0 <= rpt.full_throttle_pct <= 100

    def test_coast_time_pct_bounded(self, demo_data):
        rpt = DrivingStyleAnalyzer().analyze(demo_data)
        assert 0 <= rpt.coast_time_pct <= 100
