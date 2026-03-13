"""Tests for core.pdf_report — generate_pdf_report and chart helpers."""
import os
import pytest

from core.ibt_parser import load_demo_data
from core.analysis_engine import AnalysisEngine
from core.advanced_analysis import (
    SectorAnalyzer, BestLapAnalyzer, StintAnalyzer,
)
from core.driving_style import DrivingStyleAnalyzer
from core.pdf_report import generate_pdf_report, _make_laptime_chart, _make_sector_chart


@pytest.fixture
def full_analysis():
    """Return (data, report, sector, best, stint, style) from demo data."""
    data = load_demo_data()
    rpt = AnalysisEngine().analyze(data)
    sec = SectorAnalyzer().analyze(data, 3)
    best = BestLapAnalyzer().analyze(data)
    stint = StintAnalyzer().analyze(data)
    style = DrivingStyleAnalyzer().analyze(data)
    return data, rpt, sec, best, stint, style


class TestGeneratePdfReport:
    def test_basic_generation(self, full_analysis, tmp_path):
        data, rpt, sec, best, stint, style = full_analysis
        out = tmp_path / "report.pdf"
        result = generate_pdf_report(
            output_path=str(out), data=data, report=rpt,
            sector_report=sec, best_report=best,
            tire_deg=stint, driver_report=style,
        )
        assert result == str(out)
        assert out.exists()
        assert out.stat().st_size > 1000  # non-trivial PDF

    def test_minimal_args(self, tmp_path):
        """Generate with only required args — no optional reports."""
        data = load_demo_data()
        rpt = AnalysisEngine().analyze(data)
        out = tmp_path / "minimal.pdf"
        result = generate_pdf_report(output_path=str(out), data=data, report=rpt)
        assert out.exists()
        assert out.stat().st_size > 500

    def test_with_ai_text(self, full_analysis, tmp_path):
        data, rpt, sec, best, stint, style = full_analysis
        out = tmp_path / "ai.pdf"
        generate_pdf_report(
            output_path=str(out), data=data, report=rpt,
            sector_report=sec, best_report=best,
            tire_deg=stint, driver_report=style,
            ai_text="**Setup Change 1**\nReduce rear wing by 2 clicks.\n\nThis will improve top speed.",
        )
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_creates_parent_dirs(self, full_analysis, tmp_path):
        data, rpt, *_ = full_analysis
        out = tmp_path / "sub" / "dir" / "report.pdf"
        generate_pdf_report(output_path=str(out), data=data, report=rpt)
        assert out.exists()


class TestChartHelpers:
    def test_laptime_chart_returns_image(self, full_analysis):
        _, rpt, _, best, _, _ = full_analysis
        img = _make_laptime_chart(rpt, best)
        assert img is not None

    def test_laptime_chart_too_few_laps(self):
        from core.analysis_engine import AnalysisReport
        from core.advanced_analysis import BestLapReport
        rpt = AnalysisReport(lap_times=[90.0])
        best = BestLapReport(lap_times=[90.0], actual_best=90.0)
        assert _make_laptime_chart(rpt, best) is None

    def test_sector_chart_returns_image(self, full_analysis):
        _, _, sec, _, _, _ = full_analysis
        img = _make_sector_chart(sec)
        assert img is not None

    def test_sector_chart_empty(self):
        from core.advanced_analysis import SectorAnalysisReport
        rpt = SectorAnalysisReport()
        assert _make_sector_chart(rpt) is None
