"""Tests for core.consistency_score — Lap Consistency Score."""
import numpy as np
import pytest

from core.consistency_score import compute_consistency, ConsistencyBreakdown


# ── Basic computation ───────────────────────────────────────────────

class TestComputeConsistency:
    def test_returns_breakdown(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        rpt = AnalysisEngine().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask)
        assert isinstance(cs, ConsistencyBreakdown)

    def test_overall_in_range(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        rpt = AnalysisEngine().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask)
        assert 0 <= cs.overall <= 100

    def test_sub_scores_in_range(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        rpt = AnalysisEngine().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask)
        for score in [cs.lap_time_score, cs.sector_score, cs.corner_score,
                      cs.brake_point_score, cs.speed_score]:
            assert 0 <= score <= 100

    def test_has_notes(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        rpt = AnalysisEngine().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask)
        assert len(cs.notes) >= 1

    def test_insufficient_laps(self):
        cs = compute_consistency([90.0])
        assert cs.overall == 50.0
        assert "at least 2" in cs.notes[0].lower()

    def test_empty_laps(self):
        cs = compute_consistency([])
        assert cs.overall == 50.0

    def test_perfect_consistency(self):
        cs = compute_consistency([90.0, 90.0, 90.0, 90.0])
        assert cs.lap_time_score >= 95  # near-zero std

    def test_poor_consistency(self):
        cs = compute_consistency([85.0, 90.0, 95.0, 100.0, 105.0])
        assert cs.lap_time_score < 70


# ── With sector data ──────────────────────────────────────────────

class TestWithSectorData:
    def test_sector_score_populated(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        from core.advanced_analysis import SectorAnalyzer
        rpt = AnalysisEngine().analyze(demo_data)
        sec = SectorAnalyzer().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask, sector_report=sec)
        assert cs.sector_score > 0

    def test_worst_sector_identified(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        from core.advanced_analysis import SectorAnalyzer
        rpt = AnalysisEngine().analyze(demo_data)
        sec = SectorAnalyzer().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask, sector_report=sec)
        assert cs.worst_sector >= 1


# ── With corner data ──────────────────────────────────────────────

class TestWithCornerData:
    def test_corner_score_populated(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        from core.corner_analysis import CornerAnalyzer
        rpt = AnalysisEngine().analyze(demo_data)
        cor = CornerAnalyzer().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask, corner_report=cor)
        if cor.corners:
            assert cs.corner_score > 0

    def test_brake_point_score_populated(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        from core.corner_analysis import CornerAnalyzer
        rpt = AnalysisEngine().analyze(demo_data)
        cor = CornerAnalyzer().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask, corner_report=cor)
        if cor.corners:
            assert cs.brake_point_score > 0


# ── Full pipeline ─────────────────────────────────────────────────

class TestFullPipeline:
    def test_all_data_sources(self, demo_data):
        from core.analysis_engine import AnalysisEngine
        from core.advanced_analysis import SectorAnalyzer
        from core.corner_analysis import CornerAnalyzer
        from core.driving_style import DrivingStyleAnalyzer
        rpt = AnalysisEngine().analyze(demo_data)
        sec = SectorAnalyzer().analyze(demo_data)
        cor = CornerAnalyzer().analyze(demo_data)
        sty = DrivingStyleAnalyzer().analyze(demo_data)
        cs = compute_consistency(rpt.lap_times, rpt.valid_lap_mask,
                                 sector_report=sec, corner_report=cor,
                                 style_report=sty)
        assert cs.overall > 0
        assert cs.grade in ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "F")

    def test_grade_property(self):
        cs = ConsistencyBreakdown(overall=95)
        assert cs.grade == "A+"
        cs2 = ConsistencyBreakdown(overall=42)
        assert cs2.grade == "F"

    def test_color_hint(self):
        assert ConsistencyBreakdown(overall=90).color_hint == "green"
        assert ConsistencyBreakdown(overall=75).color_hint == "yellow"
        assert ConsistencyBreakdown(overall=50).color_hint == "red"

    def test_valid_mask_filters_outliers(self):
        times = [90.0, 90.5, 91.0, 120.0]  # last is an outlier
        mask = [True, True, True, False]
        cs = compute_consistency(times, mask)
        cs_no_mask = compute_consistency(times)
        # With mask should be more consistent
        assert cs.lap_time_score > cs_no_mask.lap_time_score
