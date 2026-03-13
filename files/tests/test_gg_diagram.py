"""Tests for G-G diagram per corner."""
import pytest
import numpy as np
from core.gg_diagram import analyze_gg_per_corner, GGReport, CornerGG


class TestAnalyzeGGPerCorner:
    def test_basic_analysis(self, demo_data):
        report = analyze_gg_per_corner(demo_data)
        assert report is not None
        assert isinstance(report, GGReport)
        assert len(report.corners) > 0

    def test_corner_fields(self, demo_data):
        report = analyze_gg_per_corner(demo_data)
        assert report is not None
        for c in report.corners:
            assert c.corner_num > 0
            assert len(c.lat_g) > 0
            assert len(c.long_g) == len(c.lat_g)
            assert c.max_lat_g > 0
            assert c.max_combined_g > 0
            assert 0 <= c.utilization_pct <= 100

    def test_with_custom_corners(self, demo_data):
        zones = [(0.1, 0.15, 0.22), (0.4, 0.45, 0.55)]
        report = analyze_gg_per_corner(demo_data, corner_zones=zones)
        assert report is not None
        assert len(report.corners) <= 2

    def test_overall_stats(self, demo_data):
        report = analyze_gg_per_corner(demo_data)
        assert report is not None
        assert report.overall_max_lat >= 0
        assert report.overall_max_long >= 0
        assert report.overall_max_combined >= 0
        assert 0 <= report.overall_utilization <= 100

    def test_findings(self, demo_data):
        report = analyze_gg_per_corner(demo_data)
        assert report is not None
        assert len(report.findings) > 0

    def test_empty_data(self):
        from core.ibt_parser import TelemetryData
        d = TelemetryData()
        d.num_laps = 0
        d.lap_boundaries = [0]
        assert analyze_gg_per_corner(d) is None

    def test_combined_g_correct(self, demo_data):
        report = analyze_gg_per_corner(demo_data)
        if report and report.corners:
            c = report.corners[0]
            # Verify max combined matches actual data
            combined = np.sqrt(c.lat_g**2 + c.long_g**2)
            assert c.max_combined_g == pytest.approx(float(np.max(combined)), abs=0.01)
