"""Tests for racing line reconstruction."""
import pytest
import numpy as np
from core.racing_line import reconstruct_racing_line, speed_colormap, RacingLine


class TestReconstructRacingLine:
    def test_basic_reconstruction(self, demo_data):
        line = reconstruct_racing_line(demo_data, 0)
        assert line is not None
        assert isinstance(line, RacingLine)
        assert len(line.x) > 0
        assert len(line.y) == len(line.x)
        assert len(line.speed) == len(line.x)
        assert line.lap_idx == 0

    def test_all_laps(self, demo_data):
        for i in range(demo_data.num_laps):
            line = reconstruct_racing_line(demo_data, i)
            assert line is not None

    def test_invalid_lap(self, demo_data):
        assert reconstruct_racing_line(demo_data, -1) is None
        assert reconstruct_racing_line(demo_data, 999) is None

    def test_path_has_extent(self, demo_data):
        """The reconstructed path should cover some area."""
        line = reconstruct_racing_line(demo_data, 0)
        assert line is not None
        # Path should have significant extent
        x_range = np.max(line.x) - np.min(line.x)
        y_range = np.max(line.y) - np.min(line.y)
        assert x_range > 0 or y_range > 0

    def test_speed_range(self, demo_data):
        line = reconstruct_racing_line(demo_data, 0)
        assert line is not None
        assert np.min(line.speed) >= 0
        assert np.max(line.speed) < 200


class TestSpeedColormap:
    def test_basic(self):
        speed = np.array([10, 30, 50, 70, 90])
        colors = speed_colormap(speed)
        assert colors.shape == (5, 4)
        assert np.all(colors >= 0)
        assert np.all(colors <= 1)

    def test_empty(self):
        colors = speed_colormap(np.array([]))
        assert colors.shape == (0, 4)

    def test_constant_speed(self):
        speed = np.full(10, 50.0)
        colors = speed_colormap(speed)
        assert colors.shape == (10, 4)
