"""Tests for multi-session aggregation."""
import pytest
import numpy as np
from core.session_aggregator import aggregate_sessions, AggregationReport
from core.ibt_parser import load_demo_data
from core.analysis_engine import AnalysisEngine, AnalysisReport


class TestAggregation:
    @pytest.fixture
    def two_sessions(self):
        d1 = load_demo_data()
        d2 = load_demo_data()
        # Tweak second session to have different lap times
        d2.lap_times = [t - 0.5 for t in d2.lap_times]
        d2.car_name = "ferrari_296_gt3"
        r1 = AnalysisEngine().analyze(d1)
        r2 = AnalysisReport(best_lap=min(d2.lap_times), avg_lap=sum(d2.lap_times)/len(d2.lap_times), lap_times=d2.lap_times)
        return [(d1, r1), (d2, r2)]

    def test_basic_aggregation(self, two_sessions):
        report = aggregate_sessions(two_sessions)
        assert report is not None
        assert report.num_sessions == 2
        assert len(report.summaries) == 2

    def test_trends(self, two_sessions):
        report = aggregate_sessions(two_sessions)
        assert report is not None
        assert len(report.best_lap_trend) == 2
        assert len(report.avg_lap_trend) == 2
        assert len(report.consistency_trend) == 2

    def test_improvement_tracked(self, two_sessions):
        report = aggregate_sessions(two_sessions)
        assert report is not None
        # Second session is faster, so improvement should be positive
        assert report.total_improvement > 0
        assert report.improving is True

    def test_single_session_returns_none(self):
        d = load_demo_data()
        r = AnalysisEngine().analyze(d)
        assert aggregate_sessions([(d, r)]) is None

    def test_empty_returns_none(self):
        assert aggregate_sessions([]) is None

    def test_car_track_grouping(self, two_sessions):
        report = aggregate_sessions(two_sessions)
        assert report is not None
        assert len(report.car_track_combos) >= 1

    def test_findings_generated(self, two_sessions):
        report = aggregate_sessions(two_sessions)
        assert report is not None
        assert len(report.findings) > 0

    def test_session_summary_fields(self, two_sessions):
        report = aggregate_sessions(two_sessions)
        assert report is not None
        s = report.summaries[0]
        assert s.num_laps > 0
        assert s.best_lap > 0
        assert s.avg_lap > 0
        assert s.consistency_pct >= 0
