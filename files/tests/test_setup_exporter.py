"""Tests for SetupExporter — HTM and JSON export, round-trip validation."""
import json
import pytest

from core.setup_parser import SetupParser, SetupExporter, ParsedSetup, create_demo_setup


@pytest.fixture
def exporter():
    return SetupExporter()


@pytest.fixture
def demo():
    return create_demo_setup("ferrari_296_gt3", "Sebring International Raceway")


class TestExportHtm:
    def test_creates_file(self, exporter, demo, tmp_path):
        out = tmp_path / "test.htm"
        result = exporter.export_htm(demo, str(out))
        assert result == str(out)
        assert out.exists()
        assert out.stat().st_size > 100

    def test_html_contains_car(self, exporter, demo, tmp_path):
        out = tmp_path / "test.htm"
        exporter.export_htm(demo, str(out))
        html = out.read_text(encoding="utf-8")
        assert "ferrari_296_gt3" in html

    def test_html_has_sections(self, exporter, demo, tmp_path):
        out = tmp_path / "test.htm"
        exporter.export_htm(demo, str(out))
        html = out.read_text(encoding="utf-8")
        assert "<table>" in html
        assert "Tires" in html or "Alignment" in html

    def test_round_trip(self, exporter, demo, tmp_path):
        """Export to HTM then re-parse — flat keys should be preserved."""
        out = tmp_path / "roundtrip.htm"
        exporter.export_htm(demo, str(out))
        reparsed = SetupParser().parse_file(str(out))
        # Key params should survive the round trip
        for key in ("LF Cold Pressure", "RF Cold Pressure", "LR Cold Pressure", "RR Cold Pressure"):
            assert reparsed.get(key) == demo.get(key), f"{key} changed after round-trip"

    def test_applies_changes(self, exporter, demo, tmp_path):
        out = tmp_path / "changed.htm"
        exporter.export_htm(demo, str(out), changes={"LF Cold Pressure": "99.0 psi"})
        assert demo.get("LF Cold Pressure") == "99.0 psi"

    def test_creates_parent_dirs(self, exporter, demo, tmp_path):
        out = tmp_path / "sub" / "dir" / "export.htm"
        exporter.export_htm(demo, str(out))
        assert out.exists()


class TestExportJson:
    def test_creates_file(self, exporter, demo, tmp_path):
        out = tmp_path / "test.json"
        exporter.export_json(demo, str(out))
        assert out.exists()

    def test_valid_json(self, exporter, demo, tmp_path):
        out = tmp_path / "test.json"
        exporter.export_json(demo, str(out))
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_matches_to_dict(self, exporter, demo, tmp_path):
        out = tmp_path / "test.json"
        exporter.export_json(demo, str(out))
        data = json.loads(out.read_text())
        expected = demo.to_dict()
        assert data["car"] == expected["car"]
        assert data["track"] == expected["track"]
