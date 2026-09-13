"""The arithmetic, checked without a network."""
import pytest

from benchmark.metrics import availability, latency, percentile


def test_percentile_is_nearest_rank():
    v = [float(i) for i in range(1, 101)]
    assert percentile(v, 50) == 50.0
    assert percentile(v, 90) == 90.0
    assert percentile(v, 100) == 100.0
    assert percentile([7.0], 50) == 7.0


def test_percentile_rejects_nonsense():
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1.0], 0)


def test_latency_refuses_a_small_sample():
    assert latency([1.0] * 29, "k", "m") is None
    assert latency([1.0] * 30, "k", "m") is not None


def test_availability_refuses_a_short_run():
    assert availability(400, 400, 0, "m") is None
    assert availability(500, 500, 0, "m") is not None


def test_throttled_probes_leave_the_denominator():
    """The bug this pins: counting 429s as failures reported 92% for a service that was up."""
    m = availability(ok=520, total=560, throttled=40, method="m")
    assert m is not None
    assert m.value == "100.00"
    assert m.n == 520
    assert "rate-limited" in m.caveats[0]


def test_a_short_run_after_throttling_publishes_nothing():
    assert availability(ok=499, total=540, throttled=41, method="m") is None
