"""Tests for core.corner_analysis — CornerDetector, CornerAnalyzer, LapDeltaAnalyzer."""
import numpy as np
import pytest

from core.corner_analysis import (
    CornerDetector, CornerAnalyzer, CornerAnalysisReport, CornerData,
    LapDeltaAnalyzer, LapDelta, format_corner_summary,
)


# ── CornerDetector ──────────────────────────────────────────────────

class TestCornerDetector:
    def test_detect_returns_list(self, demo_data):
        zones = CornerDetector().detect(demo_data, 0)
        assert isinstance(zones, list)

    def test_each_zone_is_3_tuple(self, demo_data):
        zones = CornerDetector().detect(demo_data, 0)
        for z in zones:
            assert len(z) == 3
            brake_pct, apex_pct, exit_pct = z
            assert 0 <= brake_pct <= 1
            assert 0 <= apex_pct <= 1
            assert 0 <= exit_pct <= 1

    def test_apex_between_brake_and_exit(self, demo_data):
        zones = CornerDetector().detect(demo_data, 0)
        for brake_pct, apex_pct, exit_pct in zones:
            assert brake_pct <= apex_pct <= exit_pct

    def test_invalid_lap_returns_empty(self, demo_data):
        assert CornerDetector().detect(demo_data, 999) == []

    def test_zones_ordered_by_distance(self, demo_data):
        zones = CornerDetector().detect(demo_data, 0)
        if len(zones) >= 2:
            for i in range(len(zones) - 1):
                assert zones[i][0] < zones[i + 1][0]


# ── CornerAnalyzer ──────────────────────────────────────────────────

class TestCornerAnalyzer:
    def test_returns_report(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        assert isinstance(rpt, CornerAnalysisReport)

    def test_corners_have_data(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        for cd in rpt.corners:
            assert isinstance(cd, CornerData)
            assert cd.corner_num >= 1

    def test_coaching_notes_populated(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        for cd in rpt.corners:
            assert isinstance(cd.coaching_note, str)
            assert len(cd.coaching_note) > 0

    def test_total_time_lost_nonneg(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        assert rpt.total_time_lost >= 0

    def test_corner_data_properties(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        for cd in rpt.corners:
            assert cd.best_time >= 0
            assert cd.avg_time >= 0
            assert cd.time_delta >= 0
            assert 0 <= cd.consistency_pct <= 100

    def test_lap_speeds_populated(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        if rpt.corners:
            cd = rpt.corners[0]
            assert len(cd.lap_entry_speeds) > 0
            assert len(cd.lap_min_speeds) > 0
            assert len(cd.lap_exit_speeds) > 0


# ── LapDeltaAnalyzer ───────────────────────────────────────────────

class TestLapDeltaAnalyzer:
    def test_analyze_returns_delta(self, demo_data):
        if demo_data.num_laps < 2:
            pytest.skip("Need >= 2 laps")
        result = LapDeltaAnalyzer().analyze(demo_data, 0, 1)
        assert result is not None
        assert isinstance(result, LapDelta)

    def test_delta_arrays_same_length(self, demo_data):
        if demo_data.num_laps < 2:
            pytest.skip("Need >= 2 laps")
        result = LapDeltaAnalyzer().analyze(demo_data, 0, 1)
        assert len(result.dist_pct) == len(result.delta_s)

    def test_delta_starts_near_zero(self, demo_data):
        if demo_data.num_laps < 2:
            pytest.skip("Need >= 2 laps")
        result = LapDeltaAnalyzer().analyze(demo_data, 0, 1)
        assert abs(result.delta_s[0]) < 1.0  # should start near zero

    def test_same_lap_delta_is_zero(self, demo_data):
        result = LapDeltaAnalyzer().analyze(demo_data, 0, 0)
        if result is not None:
            assert np.allclose(result.delta_s, 0, atol=0.01)

    def test_invalid_lap_returns_none(self, demo_data):
        result = LapDeltaAnalyzer().analyze(demo_data, 999, 0)
        assert result is None

    def test_segments_have_notes(self, demo_data):
        if demo_data.num_laps < 2:
            pytest.skip("Need >= 2 laps")
        best = int(np.argmin(demo_data.lap_times))
        cmp = 1 if best != 1 else 0
        result = LapDeltaAnalyzer().analyze(demo_data, best, cmp)
        if result and result.segments:
            for seg in result.segments:
                assert 'note' in seg
                assert isinstance(seg['note'], str)
                assert len(seg['note']) > 0

    def test_ref_and_cmp_lap_stored(self, demo_data):
        if demo_data.num_laps < 2:
            pytest.skip("Need >= 2 laps")
        result = LapDeltaAnalyzer().analyze(demo_data, 0, 1)
        assert result.ref_lap == 0
        assert result.cmp_lap == 1


# ── format_corner_summary ──────────────────────────────────────────

class TestFormatCornerSummary:
    def test_returns_string(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        text = format_corner_summary(rpt)
        assert isinstance(text, str)

    def test_contains_corner_labels(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        text = format_corner_summary(rpt)
        if rpt.corners:
            # Labels are named corners ("Turn 5") when known, else "T<n>".
            assert any(c.label in text for c in rpt.corners)

    def test_contains_worst_corner(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        text = format_corner_summary(rpt)
        if rpt.corners:
            assert "Worst corner" in text

    def test_empty_report_returns_empty(self):
        text = format_corner_summary(CornerAnalysisReport())
        assert text == ""

    def test_none_report_returns_empty(self):
        text = format_corner_summary(None)
        assert text == ""

    def test_includes_speed_data(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        text = format_corner_summary(rpt)
        if rpt.corners:
            assert "km/h" in text

    def test_includes_time_lost(self, demo_data):
        rpt = CornerAnalyzer().analyze(demo_data)
        text = format_corner_summary(rpt)
        if rpt.corners:
            assert "Total time lost" in text


# ── AI Prompt Integration ──────────────────────────────────────────

class TestAIPromptWithCorners:
    def test_build_prompt_with_corner_report(self, demo_data):
        """Verify _build_prompt accepts corner_report and includes corner data."""
        from core.analysis_engine import AnalysisEngine
        from core.ai_advisor import _build_prompt

        rpt = AnalysisEngine().analyze(demo_data)
        corner_rpt = CornerAnalyzer().analyze(demo_data)
        prompt = _build_prompt(rpt, demo_data.car_name, demo_data.track_name,
                               None, None, None, None, None,
                               corner_report=corner_rpt)
        assert "Corner-by-Corner Analysis" in prompt
        if corner_rpt.corners:
            # Corner labels (named corners or "T<n>") are embedded in the prompt.
            assert any(c.label in prompt for c in corner_rpt.corners)

    def test_build_prompt_without_corner_report(self, demo_data):
        """Verify _build_prompt still works without corner_report."""
        from core.analysis_engine import AnalysisEngine
        from core.ai_advisor import _build_prompt

        rpt = AnalysisEngine().analyze(demo_data)
        prompt = _build_prompt(rpt, demo_data.car_name, demo_data.tra