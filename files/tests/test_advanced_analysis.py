"""Tests for core.advanced_analysis — Sector, BestLap, Stint, History, FuelStrategy."""
import os, json, tempfile
import numpy as np
import pytest

from core.advanced_analysis import (
    SectorAnalyzer, SectorAnalysisReport,
    BestLapAnalyzer, BestLapReport,
    StintAnalyzer, TireDegReport,
    HistoryTracker, HistoryEntry,
    FuelStrategyAnalyzer, FuelStrategyReport,
    DEG_OUTLIER_S, MIN_STINT_LAPS,
)


# ── SectorAnalyzer ──────────────────────────────────────────────────

class TestSectorAnalyzer:
    def test_returns_report(self, demo_data):
        rpt = SectorAnalyzer().analyze(demo_data)
        assert isinstance(rpt, SectorAnalysisReport)

    def test_default_3_sectors(self, demo_data):
        rpt = SectorAnalyzer().analyze(demo_data)
        assert rpt.num_sectors == 3

    def test_theoretical_best_le_actual(self, demo_data):
        rpt = SectorAnalyzer().analyze(demo_data)
        if rpt.theoretical_best > 0 and rpt.actual_best > 0:
            assert rpt.theoretical_best <= rpt.actual_best + 0.001

    def test_time_left_on_table_nonneg(self, demo_data):
        rpt = SectorAnalyzer().analyze(demo_data)
        assert rpt.time_left_on_table >= 0


# ── BestLapAnalyzer ─────────────────────────────────────────────────

class TestBestLapAnalyzer:
    def test_returns_report(self, demo_data):
        rpt = BestLapAnalyzer().analyze(demo_data)
        assert isinstance(rpt, BestLapReport)

    def test_lap_count_matches(self, demo_data):
        rpt = BestLapAnalyzer().analyze(demo_data)
        assert len(rpt.lap_times) == demo_data.num_laps

    def test_fuel_per_lap_nonneg(self, demo_data):
        rpt = BestLapAnalyzer().analyze(demo_data)
        assert rpt.fuel_per_lap_kg >= 0


# ── StintAnalyzer ───────────────────────────────────────────────────

class TestStintAnalyzer:
    def test_returns_report(self, demo_data):
        rpt = StintAnalyzer().analyze(demo_data)
        assert isinstance(rpt, TireDegReport)

    def test_deg_rate_is_float(self, demo_data):
        rpt = StintAnalyzer().analyze(demo_data)
        assert isinstance(rpt.deg_rate, float)


# ── HistoryTracker ──────────────────────────────────────────────────

class TestHistoryTracker:
    def test_add_and_get(self, tmp_path):
        db = tmp_path / "history.json"
        ht = HistoryTracker(str(db))
        ht.add_entry("gt3_car", "Spa", 120.5, {"wing": "5"}, "test run")
        entries = ht.get_history("gt3_car", "Spa")
        assert len(entries) == 1
        assert entries[0].best_lap == 120.5

    def test_clear(self, tmp_path):
        db = tmp_path / "history.json"
        ht = HistoryTracker(str(db))
        ht.add_entry("gt3_car", "Spa", 120.5, {}, "")
        ht.clear()
        assert ht.get_history("gt3_car", "Spa") == []

    def test_persistence(self, tmp_path):
        db = tmp_path / "history.json"
        ht1 = HistoryTracker(str(db))
        ht1.add_entry("car", "track", 99.0, {}, "")
        # Reload from disk
        ht2 = HistoryTracker(str(db))
        assert len(ht2.get_history("car", "track")) == 1

    def test_prune_respects_max(self, tmp_path):
        db = tmp_path / "history.json"
        ht = HistoryTracker(str(db))
        for i in range(ht.MAX_PER_COMBO + 10):
            ht.add_entry("car", "track", 90.0 + i * 0.01, {}, "")
        # Pruning triggers on reload, not during add_entry
        ht2 = HistoryTracker(str(db))
        entries = ht2.get_history("car", "track")
        assert len(entries) <= ht2.MAX_PER_COMBO

    def test_find_last_returns_newest(self, tmp_path):
        """After prune sorts newest-first, _find_last must still return the most recent."""
        db = tmp_path / "history.json"
        ht = HistoryTracker(str(db))
        ht.add_entry("car", "Spa", 91.0, {"wing": "3"}, "old")
        ht.add_entry("car", "Spa", 90.0, {"wing": "5"}, "new")
        last = ht._find_last("car", "Spa")
        assert last is not None
        assert last.notes == "new"
        assert last.setup_snapshot["wing"] == "5"

    def test_changes_diff_against_newest(self, tmp_path):
        """add_entry should diff against the most recent match, not the oldest."""
        db = tmp_path / "history.json"
        ht = HistoryTracker(str(db))
        ht.add_entry("car", "Spa", 91.0, {"wing": "3"}, "")
        ht.add_entry("car", "Spa", 90.0, {"wing": "5"}, "")
        entry = ht.add_entry("car", "Spa", 89.0, {"wing": "7"}, "")
        # Should diff against wing=5 (most recent), not wing=3 (oldest)
        assert any(c['before'] == '5' and c['after'] == '7' for c in entry.changes_from_prev)


# ── FuelStrategyAnalyzer ────────────────────────────────────────────

class TestFuelStrategyAnalyzer:
    def test_returns_report(self, demo_data):
        rpt = FuelStrategyAnalyzer().analyze(demo_data, race_laps=30)
        assert isinstance(rpt, FuelStrategyReport)

    def test_fuel_per_lap_positive(self, demo_data):
        rpt = FuelStrategyAnalyzer().analyze(demo_data, race_laps=30)
        assert rpt.fuel_per_lap_l > 0

    def test_zero_race_laps(self, demo_data):
        rpt = FuelStrategyAnalyzer().analyze(demo_data, race_laps=0)
        assert isinstance(rpt, FuelStrategyReport)
