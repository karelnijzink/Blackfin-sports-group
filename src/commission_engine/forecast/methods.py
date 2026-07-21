"""Projection methods: pure functions on list[float] monthly values.

Each returns the next `horizon` projected monthly values in order. No I/O,
no state, no fallbacks: a series a method cannot honestly handle raises
ValueError, and the engine reports that instead of substituting a number.
"""


def _check_horizon(horizon: int) -> None:
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1 month, got {horizon}")


def run_rate(values: list[float], window: int, horizon: int = 12) -> list[float]:
    """Average of the trailing `window` months, held flat."""
    _check_horizon(horizon)
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if len(values) < window:
        raise ValueError(f"need at least {window} months of history, got {len(values)}")
    avg = sum(values[-window:]) / window
    return [avg] * horizon


def blend(values: list[float], windows: tuple[int, int] = (3, 6), horizon: int = 12) -> list[float]:
    """Month-by-month mean of two trailing run-rates (default 3-mo and 6-mo)."""
    first = run_rate(values, window=windows[0], horizon=horizon)
    second = run_rate(values, window=windows[1], horizon=horizon)
    return [(a + b) / 2 for a, b in zip(first, second, strict=True)]


def linear_trend(values: list[float], horizon: int = 12) -> list[float]:
    """Least-squares straight line through all history, continued forward."""
    _check_horizon(horizon)
    n = len(values)
    if n < 2:
        raise ValueError(f"need at least 2 months of history, got {n}")
    xs = range(n)
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=True)) / denominator
    intercept = y_mean - slope * x_mean
    return [intercept + slope * x for x in range(n, n + horizon)]


def geometric_growth(values: list[float], horizon: int = 12) -> list[float]:
    """Compound month-over-month growth: the geometric mean of the observed
    MoM ratios (equivalently (last/first)^(1/(n-1))), rolled forward from the
    last observed month."""
    _check_horizon(horizon)
    n = len(values)
    if n < 2:
        raise ValueError(f"need at least 2 months of history, got {n}")
    first, last = values[0], values[-1]
    if first <= 0 or last <= 0:
        raise ValueError(
            "geometric growth is undefined for non-positive endpoint months "
            f"(first={first}, last={last})"
        )
    growth = (last / first) ** (1 / (n - 1))
    return [last * growth**k for k in range(1, horizon + 1)]
