"""Tests for core.track_zones — Throttle/Brake zone classification."""
import numpy as np
import pytest

from core.track_zones import (
    classify_zones, BRAKE_THRESHOLD, THROTTLE_THRESHOLD,
    COLOR_BRAKE, COLOR_THROTTLE, COLOR_COAST,
)


class TestClassifyZones:
    def test_all_braking(self):
        thr = np.zeros(100)
        brk = np.ones(100)
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert colors.shape == (100, 4)
        assert bp == pytest.approx(100.0)
        assert tp == pytest.approx(0.0)
        assert cp == pytest.approx(0.0)
        np.testing.assert_array_almost_equal(colors[0], COLOR_BRAKE)

    def test_all_throttle(self):
        thr = np.ones(100)
        brk = np.zeros(100)
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert tp == pytest.approx(100.0)
        assert bp == pytest.approx(0.0)
        np.testing.assert_array_almost_equal(colors[0], COLOR_THROTTLE)

    def test_all_coast(self):
        thr = np.full(100, 0.1)   # below throttle threshold
        brk = np.full(100, 0.05)  # below brake threshold
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert cp == pytest.approx(100.0)
        assert tp == pytest.approx(0.0)
        assert bp == pytest.approx(0.0)
        np.testing.assert_array_almost_equal(colors[0], COLOR_COAST)

    def test_mixed_zones(self):
        thr = np.array([0.8, 0.8, 0.0, 0.0, 0.2])  # 2 throttle, 0, 0, 1 coast
        brk = np.array([0.0, 0.0, 0.5, 0.5, 0.0])   # 0, 0, 2 brake, 0
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert bp == pytest.approx(40.0)   # 2/5
        assert tp == pytest.approx(40.0)   # 2/5
        assert cp == pytest.approx(20.0)   # 1/5
        np.testing.assert_array_almost_equal(colors[0], COLOR_THROTTLE)
        np.testing.assert_array_almost_equal(colors[2], COLOR_BRAKE)
        np.testing.assert_array_almost_equal(colors[4], COLOR_COAST)

    def test_brake_overrides_throttle(self):
        """When both brake and throttle are applied, brake takes priority."""
        thr = np.array([1.0])
        brk = np.array([0.5])
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert bp == pytest.approx(100.0)
        assert tp == pytest.approx(0.0)
        np.testing.assert_array_almost_equal(colors[0], COLOR_BRAKE)

    def test_threshold_boundary_brake(self):
        """Exactly at brake threshold → not braking."""
        thr = np.array([0.0])
        brk = np.array([BRAKE_THRESHOLD])
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert bp == pytest.approx(0.0)  # not above threshold

    def test_threshold_boundary_throttle(self):
        """Exactly at throttle threshold → not throttle."""
        thr = np.array([THROTTLE_THRESHOLD])
        brk = np.array([0.0])
        colors, tp, bp, cp = classify_zones(thr, brk)
        assert tp == pytest.approx(0.0)  # not above threshold

    def test_percentages_sum_to_100(self):
        rng = np.random.default_rng(42)
        thr = rng.random(500)
        brk = rng.random(500) * 0.5
        _, tp, bp, cp = classify_zones(thr, brk)
        assert tp + bp + cp == pytest.approx(100.0)

    def test_mismatched_lengths(self):
        """Shorter array determines output size."""
        thr = np.ones(50)
        brk = np.ones(30)
        colors, _, _, _ = classify_zones(thr, brk)
        assert colors.shape == (30, 4)

    def test_empty_arrays(self):
        colors, tp, bp, cp = classify_zones(np.array([]), np.array([]))
        assert colors.shape == (0, 4)
        assert tp == 0.0 and bp == 0.0 and cp == 100.0

    def test_output_shape(self):
        thr = np.random.default_rng(0).random(200)
        brk = np.random.default_rng(1).random(200)
        colors, _, _, _ = classify_zones(thr, brk)
        assert colors.shape == (200, 4)
        assert np.all((colors >= 0) & (colors <= 1))


class TestCDEFSEntry:
    """Verify the Track Map Zones entry exists in CDEFS."""
    def test_cdefs_has_zones(self):
        # Import and check CDEFS has the new entry
        import importlib
        import sys
        # Verify the string exists in the telemetry tab mixin
        import os
        mixin_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ui', 'tab_telemetry.py')
        with open(mixin_path, encoding='utf-8') as f:
            src = f.read()
        assert 'Track Map \u2014 Throttle/Brake Zones' in src
