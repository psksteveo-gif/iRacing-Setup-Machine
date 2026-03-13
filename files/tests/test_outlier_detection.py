"""Tests for outlier detection logic in the AnalysisEngine."""
import pytest
from core.analysis_engine import AnalysisEngine


class TestDetectOutliers:
    """Unit tests for AnalysisEngine._detect_outliers static method."""

    def test_all_valid_normal_laps(self):
        laps = [90.0, 90.1, 89.9, 90.2, 90.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert all(mask), "Uniform laps should all be valid"

    def test_first_lap_warmup_flagged(self):
        """First lap > 107% of median should be flagged as warmup."""
        laps = [110.0, 90.0, 89.8, 90.2, 90.1]
        mask = AnalysisEngine._detect_outliers(laps)
        assert mask[0] is False, "Slow first lap should be flagged"
        assert all(mask[1:]), "Remaining laps should be valid"

    def test_last_lap_inlap_flagged(self):
        """Last lap > 107% of median should be flagged as in-lap."""
        laps = [90.0, 89.8, 90.2, 90.1, 120.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert mask[-1] is False, "Slow last lap should be flagged"
        assert all(mask[:-1]), "Prior laps should be valid"

    def test_extreme_outlier_iqr(self):
        """An extreme outlier should be caught by IQR fence."""
        laps = [90.0, 90.1, 89.9, 90.0, 90.2, 300.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert mask[-1] is False, "300s lap should be IQR outlier"

    def test_very_fast_outlier(self):
        """A ridiculously fast lap should be caught by IQR lower fence."""
        laps = [90.0, 90.1, 89.9, 90.0, 90.2, 10.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert mask[-1] is False, "10s lap should be flagged as outlier"

    def test_two_laps_all_valid(self):
        """With fewer than 3 laps, all should be marked valid."""
        laps = [90.0, 91.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert all(mask)

    def test_single_lap_valid(self):
        laps = [90.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert all(mask)

    def test_empty_laps(self):
        mask = AnalysisEngine._detect_outliers([])
        assert mask == []

    def test_first_and_last_flagged_together(self):
        """Both warmup and in-lap can be flagged simultaneously."""
        laps = [120.0, 90.0, 89.8, 90.2, 115.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert mask[0] is False
        assert mask[-1] is False
        assert all(mask[1:-1])

    def test_tight_distribution_uses_min_spread(self):
        """When IQR is tiny, IQR_MIN_SPREAD prevents over-flagging."""
        laps = [90.0, 90.0, 90.0, 90.0, 90.0]
        mask = AnalysisEngine._detect_outliers(laps)
        assert all(mask), "Identical laps should not be flagged"
