"""Tests for SetupParser edge cases — malformed HTML and boundary inputs."""
import pytest
from core.setup_parser import SetupParser, ParsedSetup


class TestSetupParserEdgeCases:
    """Edge case tests for SetupParser.parse_html."""

    def test_empty_html_returns_setup(self):
        sp = SetupParser()
        result = sp.parse_html("", "empty.htm")
        assert isinstance(result, ParsedSetup)
        assert result.filename == "empty.htm"

    def test_minimal_html_no_crash(self):
        sp = SetupParser()
        result = sp.parse_html("<html><body></body></html>", "minimal.htm")
        assert isinstance(result, ParsedSetup)

    def test_missing_closing_tags(self):
        """Malformed HTML with missing closing tags should not crash."""
        bad_html = "<table><tr><td>Param<td>Value</table>"
        sp = SetupParser()
        result = sp.parse_html(bad_html, "bad.htm")
        assert isinstance(result, ParsedSetup)

    def test_nested_tables(self):
        html = """<table><tr><td>
            <table><tr><td>Inner Param</td><td>42</td></tr></table>
        </td></tr></table>"""
        sp = SetupParser()
        result = sp.parse_html(html, "nested.htm")
        assert isinstance(result, ParsedSetup)

    def test_html_entities(self):
        """HTML entities like &amp; should be handled."""
        html = "<table><tr><td>Front &amp; Rear</td><td>3.5</td></tr></table>"
        sp = SetupParser()
        result = sp.parse_html(html, "entities.htm")
        assert isinstance(result, ParsedSetup)

    def test_unicode_content(self):
        html = "<table><tr><td>Température</td><td>25°C</td></tr></table>"
        sp = SetupParser()
        result = sp.parse_html(html, "unicode.htm")
        assert isinstance(result, ParsedSetup)

    def test_title_extraction(self):
        html = "<html><head><title>BMW M4 GT3</title></head><body></body></html>"
        sp = SetupParser()
        result = sp.parse_html(html, "titled.htm")
        assert result.car == "BMW M4 GT3"

    def test_track_extraction(self):
        html = "<html><body>Track: Spa-Francorchamps</body></html>"
        sp = SetupParser()
        result = sp.parse_html(html, "track.htm")
        assert "Spa" in result.track

    def test_flat_dict(self):
        """flat property should return a dict."""
        sp = SetupParser()
        result = sp.parse_html(
            "<table><tr><td>Rear Wing</td><td>5</td></tr></table>",
            "flat.htm",
        )
        assert isinstance(result.flat, dict)


class TestSetupParserFileEdgeCases:

    def test_nonexistent_file(self):
        sp = SetupParser()
        with pytest.raises(FileNotFoundError):
            sp.parse_file("nonexistent_setup_xyz.htm")

    def test_oversize_file(self, tmp_path):
        """Files over MAX_SETUP_FILE_SIZE should be rejected."""
        f = tmp_path / "huge.htm"
        f.write_text("x" * 100)
        import os
        real_getsize = os.path.getsize
        os.path.getsize = lambda _: 15 * 1024 * 1024
        try:
            sp = SetupParser()
            with pytest.raises(ValueError, match="10 MB"):
                sp.parse_file(str(f))
        finally:
            os.path.getsize = real_getsize
