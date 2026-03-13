"""Tests for setup change impact predictor."""
import pytest
from core.setup_impact import predict_impact, get_available_parameters, ImpactReport


class TestPredictImpact:
    def test_single_change(self):
        report = predict_impact([{'parameter': 'rear_wing', 'delta': 1}])
        assert isinstance(report, ImpactReport)
        assert len(report.predictions) == 1
        p = report.predictions[0]
        assert p.parameter == "rear_wing"
        assert p.direction == "increase"
        assert p.magnitude == 1.0
        assert p.lap_time_delta_s != 0
        assert p.straight_speed_delta_kmh < 0  # more wing = slower straight
        assert p.corner_speed_delta_kmh > 0     # more wing = faster corners
        assert "understeer" in p.balance_shift

    def test_decrease(self):
        report = predict_impact([{'parameter': 'rear_wing', 'delta': -2}])
        p = report.predictions[0]
        assert p.direction == "decrease"
        assert p.magnitude == 2.0
        assert p.straight_speed_delta_kmh > 0   # less wing = faster straight

    def test_multiple_changes(self):
        changes = [
            {'parameter': 'rear_wing', 'delta': 1},
            {'parameter': 'front_spring', 'delta': -1},
            {'parameter': 'brake_bias', 'delta': 0.5},
        ]
        report = predict_impact(changes)
        assert len(report.predictions) == 3
        assert report.net_lap_time_delta_s != 0
        assert len(report.summary) > 0

    def test_unknown_parameter_skipped(self):
        report = predict_impact([{'parameter': 'unicorn', 'delta': 1}])
        assert len(report.predictions) == 0

    def test_zero_delta_skipped(self):
        report = predict_impact([{'parameter': 'rear_wing', 'delta': 0}])
        assert len(report.predictions) == 0

    def test_all_parameters_work(self):
        params = get_available_parameters()
        assert len(params) > 5
        for p in params:
            report = predict_impact([{'parameter': p, 'delta': 1}])
            assert len(report.predictions) == 1

    def test_confidence_range(self):
        report = predict_impact([{'parameter': 'rear_wing', 'delta': 1}])
        assert 0 <= report.predictions[0].confidence <= 1

    def test_explanation_nonempty(self):
        report = predict_impact([{'parameter': 'rear_wing', 'delta': 1}])
        assert len(report.predictions[0].explanation) > 10

    def test_net_balance(self):
        # Rear wing + front wing = competing effects
        report = predict_impact([
            {'parameter': 'rear_wing', 'delta': 1},
            {'parameter': 'front_wing', 'delta': 1},
        ])
        assert report.net_balance_shift in ("more oversteer", "more understeer", "neutral")

    def test_available_parameters(self):
        params = get_available_parameters()
        assert "rear_wing" in params
        assert "front_wing" in params
        assert "tire_pressure" in params
        assert "brake_bias" in params
