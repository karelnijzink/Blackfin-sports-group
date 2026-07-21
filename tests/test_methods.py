"""Projection methods are pure functions on list[float]: no I/O, no state."""

import pytest

from commission_engine.forecast.methods import blend, geometric_growth, linear_trend, run_rate


class TestRunRate:
    def test_constant_series_projects_flat(self):
        assert run_rate([100.0] * 6, window=3, horizon=12) == [100.0] * 12

    def test_uses_only_the_trailing_window(self):
        values = [1.0, 1.0, 1.0, 300.0, 300.0, 300.0]
        assert run_rate(values, window=3, horizon=2) == [300.0, 300.0]

    def test_window_larger_than_history_raises(self):
        with pytest.raises(ValueError):
            run_rate([100.0, 100.0], window=3)


class TestBlend:
    def test_blend_is_mean_of_run_rates(self):
        values = [0.0, 0.0, 0.0, 60.0, 60.0, 60.0]
        # 3-mo run-rate: 60/mo; 6-mo run-rate: 30/mo; blend: 45/mo
        assert blend(values, windows=(3, 6), horizon=1) == [45.0]


class TestLinearTrend:
    def test_exact_line_continues(self):
        values = [10.0, 20.0, 30.0, 40.0]
        projected = linear_trend(values, horizon=3)
        assert [round(v, 6) for v in projected] == [50.0, 60.0, 70.0]

    def test_needs_at_least_two_points(self):
        with pytest.raises(ValueError):
            linear_trend([10.0], horizon=3)


class TestGeometricGrowth:
    def test_exact_geometric_series_continues(self):
        values = [100.0, 200.0, 400.0]
        assert [round(v, 6) for v in geometric_growth(values, horizon=3)] == [800.0, 1600.0, 3200.0]

    def test_non_positive_endpoint_raises_instead_of_guessing(self):
        with pytest.raises(ValueError):
            geometric_growth([0.0, 100.0], horizon=3)
        with pytest.raises(ValueError):
            geometric_growth([100.0, 0.0], horizon=3)


def test_methods_do_not_mutate_input():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    snapshot = list(values)
    run_rate(values, window=3)
    blend(values)
    linear_trend(values)
    geometric_growth(values)
    assert values == snapshot
