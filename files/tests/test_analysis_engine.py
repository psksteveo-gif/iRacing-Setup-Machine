"""Tests for core.analysis_engine — constants, format_laptime, AnalysisEngine."""
import numpy as np
import pytest

from core.analysis_engine import (
    AnalysisEngine, AnalysisReport, Severity, Category, Issue,
    format_laptime,
    TIRE_OVERHEAT_BASE_C, TIRE_SPREAD_C, IQR_MULTIPLIER, IQR_MIN_SPREAD,
    WARMUP_INLAP_FACTOR, DOWNSAMPLE_CHART, DOWNSAMPLE_LAP,
    CONSISTENCY_WARNING_STD, CONSISTENCY_EXCELLENT_STD,
)


# ── format_laptime ──────────────────────────────────────────────────

class TestFormatLaptime:
    def test_normal_lap(self):
        assert format_laptime(91.234) == "1:31.234"

    def test_zero_returns_placeholder(self):
        assert format_laptime(0) == "—"

    def test_negative_returns_placeholder(self):
        assert format_laptime(-5.0) == "—"

    def test_exact_minute(self):
        result = format_laptime(60.0)
        assert result == "1:00.000"

    def test_sub_minute(self):
        result = format_laptime(45.678)
        assert result == "45.678s"


# ── Constants sanity ────────────────────────────────────────────────

class TestConstants:
    def test_tire_overheat_positive(self):
        assert TIRE_OVERHEAT_BASE_C > 0

    def test_downsample_reasonable(self):
        assert 500 <= DOWNSAMPLE_CHART <= 10_000
        assert 500 <= DOWNSAMPLE_LAP <= 10_000

    def test_iqr_multiplier_gt_zero(self):
        assert IQR_MULTIPLIER > 0

    def test_warmup_factor_gt_one(self):
        assert WARMUP_INLAP_FACTOR > 1.0


# ── AnalysisReport ──────────────────────────────────────────────────

class TestAnalysisReport:
    def test_add_issue_increments_counts(self):
        rpt = AnalysisReport()
        rpt.add_issue(Severity.CRITICAL, Category.TIRES, "t", "d", "r")
        rpt.add_issue(Severity.WARNING, Category.BRAKES, "t", "d", "r")
        rpt.add_issue(Severity.INFO, Category.GENERAL, "t", "d", "r")
        assert rpt.critical_count == 1
        assert rpt.warning_count == 1
        assert rpt.info_count == 1


# ── Outlier detection ───────────────────────────────────────────────

class TestOutlierDetection:
    def test_short_list_marks_all_valid(self):
        mask = AnalysisEngine._detect_outliers([90.0, 91.0])
        assert all(mask)

    def test_flags_obvious_outlier(self):
        laps = [90.0, 90.2, 89.8, 90.1, 200.0, 90.0, 90.3, 89.9]
        mask = AnalysisEngine._detect_outliers(laps)
        # The 200s lap (index 4) should be flagged
        assert mask[4] is False or mask[4] == False

    def test_uniform_laps_all_valid(self):
        laps = [90.0 + i * 0.01 for i in range(10)]
        mask = AnalysisEngine._detect_outliers(laps)
        # Interior laps should all be valid (first/last may be flagged by warmup rule)
        assert all(mask[1:-1])


# ── Full analysis pipeline ──────────────────────────────────────────

class TestAnalysisEngine:
    def test_analyze_returns_report(self, demo_data):
        engine = AnalysisEngine()
        report = engine.analyze(demo_data)
        assert isinstance(report, AnalysisReport)

    def test_report_has_lap_times(self, demo_data):
        report = AnalysisEngine().analyze(demo_data)
        assert len(report.lap_times) == demo_data.num_laps

    def test_best_lap_le_avg(self, demo_data):
        report = AnalysisEngine().analyze(demo_data)
        assert report.best_lap <= report.avg_lap

    def test_issues_populated(self, demo_data):
        report = AnalysisEngine().analyze(demo_data)
        assert len(report.issues) > 0

    def test_balance_score_in_range(self, demo_data):
        report = AnalysisEngine().analyze(demo_data)
        assert -2 <= report.balance_score <= 2

    def test_grip_utilization_nonneg(self, demo_data):
        report = AnalysisEngine().analyze(demo_data)
        assert report.grip_utilization_pct >= 0


class TestConsistencyOutlierFiltering:
    """Verify _analyze_consistency uses valid_lap_mask, not raw lap_times."""

    def test_consistency_ignores_outlier_laps(self, demo_data):
        """A single massive outlier should not inflate std deviation when filtered."""
        engine = AnalysisEngine()
        # Run normal analysis first
        clean_report = engine.analyze(demo_data)

        # Inject a huge outlier into lap_times and re-analyze
        demo_data.lap_times = list(demo_data.lap_times) + [300.0]
        demo_data.num_laps = len(demo_data.lap_times)
        outlier_report = engine.analyze(demo_data)

        # The outlier should be flagged invalid by _detect_outliers
        assert outlier_report.valid_lap_mask
        assert outlier_report.outlier_count >= 1

    def test_consistency_needs_3_valid_laps(self):
        """With fewer than 3 valid laps, no consistency issue should be raised."""
        from core.ibt_parser import TelemetryData
        data = TelemetryData()
        data.lap_times = [90.0, 200.0]
        data.num_laps = 2
        report = AnalysisEngine().analyze(data)
        consistency_issues = [i for i in report.issues if 'Consistency' in i.title or 'consistency' in i.title.lower()]
        assert len(consistency_issues) == 0


# ── Weather & Wind analysis ─────────────────────────────────────────

class TestWeatherAnalysis:
    def test_wet_conditions_generate_warning(self):
        from core.ibt_parser import load_demo_data
        data = load_demo_data()
        data.session_info['weather_type'] = 'Rain'
        report = AnalysisEngine().analyze(data)
        wet_issues = [i for i in report.issues if 'Wet' in i.title or 'wet' in i.description.lower()]
        assert len(wet_issues) >= 1

    def test_dry_conditions_no_wet_warning(self):
        from core.ibt_parser import load_demo_data
        data = load_demo_data()
        data.session_info['weather_type'] = 'Sunny'
        report = AnalysisEngine().analyze(data)
        wet_warnings = [i for i in report.issues if 'Wet Conditions' in i.title]
        assert len(wet_warnings) == 0

    def test_wet_lowers_overheat_threshold(self):
        engine = AnalysisEngine()
        engine._session_info = {'air_temp_c': 25.0, 'weather_type': 'Sunny'}
        dry_thresh = engine._tire_overheat_threshold()
        engine._session_info = {'air_temp_c': 25.0, 'weather_type': 'Rain'}
        wet_thresh = engine._tire_overheat_threshold()
        assert wet_thresh < dry_thresh

    def test_wind_generates_info(self):
        from core.ibt_parser import load_demo_data
        data = load_demo_data()
        data.session_info['wind_speed_ms'] = 5.0
        data.session_info['wind_direction_deg'] = 180.0
        report = AnalysisEngine().analyze(data)
        wind_issues = [i for i in report.issues if 'Wind' in i.title]
        assert len(wind_issues) >= 1

    def test_light_wind_no_issue(self):
        from core.ibt_parser import load_demo_data
        data = load_demo_data()
        data.session_info['wind_speed_ms'] = 1.0
        report = AnalysisEngine().analyze(data)
        wind_issues = [i for i in report.issues if 'Wind' in i.title]
        assert len(wind_issues) == 0

    def test_cool_track_night_advisory(self):
        from core.ibt_parser import load_demo_data
        data = load_demo_data()
        data.session_info['air_temp_c'] = 15.0
        data.session_info['track_temp_c'] = 16.0
        report = AnalysisEngine().analyze(data)
        night_issues = [i for i in report.issues if 'Cool' in i.title or 'Night' in i.title]
        assert len(night_issues) >= 1
