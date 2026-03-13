"""Tests for brake trace analysis."""
import pytest
import numpy as np
from core.brake_analysis import analyze_braking, BrakeAnalysisReport, BrakeProfile


class TestAnalyzeBraking:
    def test_basic_analysis(self, demo_data):
        report = analyze_braking(demo_data)
        assert report is not None
        assert isinstance(report, BrakeAnalysisReport)
        assert len(report.profiles) > 0
        assert report.overall_modulation_score > 0

    def test_profile_fields(self, demo_data):
        report = analyze_braking(demo_data)
        assert report is not None
        for p in report.profiles:
            assert p.corner_num > 0
            assert 0 <= p.initial_bite <= 1
            assert 0 <= p.peak_pressure <= 1
            assert 0 <= p.modulation_score <= 100
            assert 0 <= p.trail_brake_pct <= 100
            assert p.release_speed >= 0
            assert p.avg_brake_duration_s >= 0
            assert len(p.coaching_note) > 0

    def test_with_custom_corners(self, demo_data):
        corners = [(0.1, 0.15, 0.22), (0.4, 0.45, 0.52)]
        report = analyze_braking(demo_data, corners=corners)
        assert report is not None
        assert len(report.profiles) <= 2

    def test_weakest_corner_valid(self, demo_data):
        report = analyze_braking(demo_data)
        if report and report.profiles:
            valid_nums = {p.corner_num for p in report.profiles}
            assert report.weakest_corner in valid_nums

    def test_empty_data(self):
        from core.ibt_parser import TelemetryData
        data = TelemetryData()
        data.num_laps = 0
        data.lap_boundaries = [0]
        assert analyze_braking(data) is None

    def test_findings_generated(self, demo_data):
        report = analyze_braking(demo_data)
        if report:
            assert isinstance(report.findings, list)

    def test_per_lap_data(self, demo_data):
        report = analyze_braking(demo_data)
        if report and report.profiles:
            p = report.profiles[0]
            assert len(p.lap_initial_bites) > 0
            assert len(p.lap_peak_pressures) > 0
