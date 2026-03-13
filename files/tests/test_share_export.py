"""Tests for one-click share export."""
import os
import json
import pytest
from core.share_export import (build_share_summary, export_json,
                                export_clipboard_text, ShareSummary)
from core.analysis_engine import AnalysisEngine
from core.consistency_score import compute_consistency
from core.advanced_analysis import SectorAnalyzer, StintAnalyzer


class TestBuildShareSummary:
    def test_basic_build(self, demo_data):
        rpt = AnalysisEngine().analyze(demo_data)
        summary = build_share_summary(demo_data, rpt)
        assert isinstance(summary, ShareSummary)
        assert summary.car_name == "ferrari_296_gt3"
        assert summary.track_name == "Sebring International Raceway"
        assert summary.num_laps == 8
        assert summary.best_lap > 0
        assert summary.avg_lap > 0
        assert len(summary.lap_times) == 8

    def test_with_consistency(self, demo_data):
        rpt = AnalysisEngine().analyze(demo_data)
        cs = compute_consistency(demo_data.lap_times)
        summary = build_share_summary(demo_data, rpt, consistency=cs)
        assert summary.consistency_score > 0
        assert summary.consistency_grade != "N/A"

    def test_with_sectors(self, demo_data):
        rpt = AnalysisEngine().analyze(demo_data)
        sec = SectorAnalyzer().analyze(demo_data, 3)
        summary = build_share_summary(demo_data, rpt, sector_report=sec)
        assert len(summary.sector_times) == 3
        assert summary.theoretical_best > 0

    def test_conditions_populated(self, demo_data):
        rpt = AnalysisEngine().analyze(demo_data)
        summary = build_share_summary(demo_data, rpt)
        assert 'air_temp_c' in summary.conditions
        assert 'track_temp_c' in summary.conditions

    def test_fuel_info(self, demo_data):
        rpt = AnalysisEngine().analyze(demo_data)
        summary = build_share_summary(demo_data, rpt)
        assert 'fuel_per_lap_l' in summary.fuel_info
        assert summary.fuel_info['fuel_per_lap_l'] > 0


class TestExportJson:
    def test_export_creates_file(self, demo_data, tmp_path):
        rpt = AnalysisEngine().analyze(demo_data)
        summary = build_share_summary(demo_data, rpt)
        path = str(tmp_path / "export.json")
        result = export_json(summary, path)
        assert os.path.exists(result)
        with open(result, encoding='utf-8') as f:
            data = json.load(f)
        assert data['car_name'] == "ferrari_296_gt3"
        assert data['num_laps'] == 8
        assert isinstance(data['lap_times'], list)

    def test_json_roundtrip(self, demo_data, tmp_path):
        rpt = AnalysisEngine().analyze(demo_data)
        summary = build_share_summary(demo_data, rpt)
        path = str(tmp_path / "rt.json")
        export_json(summary, path)
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        assert d['best_lap'] == round(summary.best_lap, 3)


class TestClipboardText:
    def test_text_output(self, demo_data):
        rpt = AnalysisEngine().analyze(demo_data)
        summary = build_share_summary(demo_data, rpt)
        text = export_clipboard_text(summary)
        assert "ferrari_296_gt3" in text
        assert "Sebring" in text
        assert "Best:" in text
        assert len(text) > 50
