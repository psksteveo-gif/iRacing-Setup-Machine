"""Tests for stint strategy calculator."""
import pytest
from core.stint_strategy import calculate_strategy, StrategyReport


class TestCalculateStrategy:
    def test_basic_strategy(self):
        report = calculate_strategy(
            race_laps=30, fuel_per_lap_l=3.5, fuel_tank_capacity_l=120,
            base_lap_time_s=90.0, tire_deg_rate_s=0.03, tire_cliff_lap=25,
        )
        assert isinstance(report, StrategyReport)
        assert report.race_laps == 30
        assert report.total_race_time_s > 0
        assert len(report.stints) > 0

    def test_no_stop_possible(self):
        # Small race, big tank — 0 stops
        report = calculate_strategy(
            race_laps=10, fuel_per_lap_l=2.0, fuel_tank_capacity_l=120,
            base_lap_time_s=90.0,
        )
        assert report.num_stops == 0
        assert len(report.pit_stops) == 0
        assert len(report.stints) == 1

    def test_forced_stop(self):
        # Tiny tank forces a stop
        report = calculate_strategy(
            race_laps=20, fuel_per_lap_l=5.0, fuel_tank_capacity_l=60,
            base_lap_time_s=90.0,
        )
        assert report.num_stops >= 1
        assert len(report.pit_stops) >= 1

    def test_pit_stop_fields(self):
        report = calculate_strategy(
            race_laps=40, fuel_per_lap_l=4.0, fuel_tank_capacity_l=80,
            base_lap_time_s=90.0,
        )
        for stop in report.pit_stops:
            assert stop.lap > 0
            assert stop.fuel_to_add_l > 0
            assert stop.estimated_stop_time_s > 0

    def test_stint_plan_fields(self):
        report = calculate_strategy(
            race_laps=30, fuel_per_lap_l=3.0, fuel_tank_capacity_l=100,
            base_lap_time_s=90.0,
        )
        total_laps = sum(s.num_laps for s in report.stints)
        assert total_laps == 30
        for s in report.stints:
            assert s.start_lap >= 1
            assert s.end_lap >= s.start_lap
            assert s.fuel_start_l > 0

    def test_findings(self):
        report = calculate_strategy(
            race_laps=30, fuel_per_lap_l=3.5, fuel_tank_capacity_l=120,
            base_lap_time_s=90.0,
        )
        assert len(report.findings) > 0

    def test_race_time_minutes(self):
        report = calculate_strategy(
            race_laps=10, fuel_per_lap_l=2.0, fuel_tank_capacity_l=120,
            base_lap_time_s=90.0,
        )
        assert report.race_time_min > 0
        assert report.race_time_min == pytest.approx(report.total_race_time_s / 60.0, abs=0.01)

    def test_zero_inputs(self):
        report = calculate_strategy(race_laps=0, fuel_per_lap_l=0, fuel_tank_capacity_l=0, base_lap_time_s=0)
        assert len(report.findings) > 0
        assert report.total_race_time_s == 0

    def test_alternative_strategies(self):
        report = calculate_strategy(
            race_laps=50, fuel_per_lap_l=3.0, fuel_tank_capacity_l=100,
            base_lap_time_s=90.0,
        )
        # Should have info about alternative strategies
        assert isinstance(report.one_fewer_stop_possible, bool)
        assert isinstance(report.one_more_stop_delta_s, (int, float))
