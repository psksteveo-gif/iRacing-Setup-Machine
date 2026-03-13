"""Tests for core.setup_parser — SetupParser, create_demo_setup, SetupDiffer."""
import pytest

from core.setup_parser import SetupParser, ParsedSetup, SetupDiffer, create_demo_setup


# ── create_demo_setup ───────────────────────────────────────────────

class TestCreateDemoSetup:
    def test_returns_parsed_setup(self, demo_setup):
        assert isinstance(demo_setup, ParsedSetup)

    def test_has_sections(self, demo_setup):
        assert len(demo_setup.sections) >= 5

    def test_flat_dict_populated(self, demo_setup):
        assert len(demo_setup.flat) > 0

    def test_tire_pressures_present(self, demo_setup):
        flat = demo_setup.flat
        for key in ("LF Cold Pressure", "RF Cold Pressure", "LR Cold Pressure", "RR Cold Pressure"):
            assert key in flat, f"Missing {key} in flat dict"

    def test_car_and_track(self, demo_setup):
        assert "ferrari" in demo_setup.car.lower() or "296" in demo_setup.car
        assert "Sebring" in demo_setup.track

    def test_get_returns_value(self, demo_setup):
        val = demo_setup.get("LF Pressure")
        assert val is not None

    def test_set_updates_value(self, demo_setup):
        demo_setup.set("LF Pressure", "99.9 psi")
        assert demo_setup.get("LF Pressure") == "99.9 psi"

    def test_to_dict(self, demo_setup):
        d = demo_setup.to_dict()
        assert isinstance(d, dict)
        assert "car" in d


# ── SetupParser (HTML) ──────────────────────────────────────────────

class TestSetupParser:
    def test_parse_html_basic(self):
        html = """<html><head><title>ferrari_296_gt3 setup</title></head>
        <body><h2>Tires</h2>
        <table><tr><td>LF Pressure</td><td>24.0 psi</td></tr></table></body></html>"""
        parser = SetupParser()
        setup = parser.parse_html(html, "test_setup.htm")
        assert isinstance(setup, ParsedSetup)

    def test_parse_file_missing_raises(self, tmp_path):
        parser = SetupParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file(str(tmp_path / "missing.htm"))


# ── SetupDiffer ─────────────────────────────────────────────────────

class TestSetupDiffer:
    def test_diff_identical(self, demo_setup):
        diffs = SetupDiffer().diff(demo_setup, demo_setup)
        assert diffs == []

    def test_diff_detects_change(self):
        a = create_demo_setup("car", "track")
        b = create_demo_setup("car", "track")
        b.set("LF Cold Pressure", "99.9 psi")
        diffs = SetupDiffer().diff(a, b)
        assert len(diffs) >= 1
        changed_params = [d["param"] for d in diffs]
        assert "LF Cold Pressure" in changed_params
