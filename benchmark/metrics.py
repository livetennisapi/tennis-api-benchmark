"""Pure summarising arithmetic. No network, so the numbers can be checked without a key.

Mirrors the definitions published at https://besttennisapi.com/methodology. Three terms are kept
strictly apart, because conflating them is how latency claims become untrue:

  processing  published_at - timestamp. Time inside the provider, before the frame was sent.
  transport   received_at - published_at. Time on the wire to wherever you ran this.
  end_to_end  the sum, as seen from ONE vantage. It is NOT the delay from a point being played:
              nothing this tool can reach observes the court.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# A percentile over a handful of observations is an anecdote with a decimal point.
MIN_SAMPLE = 30
# An availability share needs a run long enough to mean something.
MIN_PROBES = 500


@dataclass(frozen=True)
class Metric:
    key: str
    value: str
    unit: str
    n: int
    method: str
    caveats: tuple[str, ...] = field(default_factory=tuple)


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile. Not interpolated: an interpolated p50 reports a latency that was
    never actually observed."""
    if not values:
        raise ValueError("percentile of an empty sample")
    if not 0 < p <= 100:
        raise ValueError(f"p must be in (0, 100], got {p}")
    ordered = sorted(values)
    rank = min(max(1, math.ceil(p / 100.0 * len(ordered))), len(ordered))
    return ordered[rank - 1]


def latency(samples: list[float], key: str, method: str,
            caveats: tuple[str, ...] = ()) -> Metric | None:
    clean = [v for v in samples if v is not None and v >= 0]
    if len(clean) < MIN_SAMPLE:
        return None
    return Metric(key=key, value=f"{percentile(clean, 50):,.0f}", unit="ms",
                  n=len(clean), method=method, caveats=caveats)


def availability(ok: int, total: int, throttled: int, method: str) -> Metric | None:
    """Observed availability. Rate-limited probes leave the denominator entirely: a 429 is the
    service working as documented and telling you to slow down, not the service being down."""
    counted = total - throttled
    if counted < MIN_PROBES:
        return None
    return Metric(
        key="availability_observed", value=f"{100.0 * ok / counted:.2f}", unit="%",
        n=counted, method=method,
        caveats=("Observed from a single vantage over a bounded window. Not an uptime "
                 "commitment and not an SLA."
                 + (f" {throttled} rate-limited probes were excluded from the denominator "
                    "rather than counted as failures." if throttled else ""),),
    )
