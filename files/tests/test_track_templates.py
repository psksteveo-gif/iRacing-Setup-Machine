"""Tests for data/templates/track_templates.py — public API coverage."""
import pytest
from data.templates.track_templates import (
    list_tracks, get_track_info, get_setup_template,
    TrackInfo, SetupTemplate,
)


class TestListTracks:
    def test_returns_sorted_list(self):
        tracks = list_tracks()
        assert isinstance(tracks, list)
        assert tracks == sorted(tracks)

    def test_contains_known_tracks(self):
        tracks = list_tracks()
        for name in ["Monza", "Spa-Francorchamps", "Sebring International Raceway"]:
            assert name in tracks

    def test_not_empty(self):
        assert len(list_tracks()) >= 10


class TestGetTrackInfo:
    def test_known_track(self):
        info = get_track_info("Monza")
        assert isinstance(info, TrackInfo)
        assert info.name == "Monza"
        assert info.downforce_demand == "low"

    def test_unknown_track_returns_none(self):
        assert get_track_info("Nonexistent Raceway") is None

    def test_all_tracks_have_valid_fields(self):
        for name in list_tracks():
            info = get_track_info(name)
            assert info is not None
            assert info.downforce_demand in ("low", "medium", "high")
            assert info.tire_stress in ("low", "medium", "high")

    def test_track_notes_are_strings(self):
        info = get_track_info("Sebring International Raceway")
        assert info is not None
        assert isinstance(info.notes, str)
        assert len(info.notes) > 0


class TestGetSetupTemplate:
    def test_gt3_medium(self):
        tmpl = get_setup_template("gt3", "Spa-Francorchamps")
        assert isinstance(tmpl, SetupTemplate)
        assert tmpl.tire_pressures_psi is not None
        assert "LF" in tmpl.tire_pressures_psi

    def test_formula_low(self):
        tmpl = get_setup_template("formula", "Monza")
        assert isinstance(tmpl, SetupTemplate)
        assert tmpl.brake_bias_pct is not None
        assert tmpl.tire_pressures_psi["LF"] < 25  # formula runs lower

    def test_gt3_high(self):
        tmpl = get_setup_template("gt3", "Suzuka International Racing Course")
        assert isinstance(tmpl, SetupTemplate)
        assert tmpl.front_wing is not None

    def test_unknown_car_class_falls_back_to_gt3(self):
        tmpl = get_setup_template("prototype", "Monza")
        gt3 = get_setup_template("gt3", "Monza")
        assert tmpl.tire_pressures_psi == gt3.tire_pressures_psi

    def test_unknown_track_uses_medium(self):
        tmpl = get_setup_template("gt3", "Unknown Track")
        medium = get_setup_template("gt3", "Watkins Glen International")  # medium track
        assert tmpl.tire_pressures_psi == medium.tire_pressures_psi

    def test_template_has_key_adjustments(self):
        tmpl = get_setup_template("gt3", "Monza")
        assert tmpl.key_adjustments is not None
        assert len(tmpl.key_adjustments) > 0

    def test_camber_values_negative(self):
        tmpl = get_setup_template("gt3", "Spa-Francorchamps")
        assert tmpl.camber_deg is not None
        for corner, val in tmpl.camber_deg.items():
            assert val < 0, f"{corner} camber should be negative"
