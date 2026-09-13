"""HTTP probes. Points at whatever base URL you give it and has no idea whose API it is."""
from __future__ import annotations

import time

import requests

UA = "tennis-api-benchmark/0.1 (+https://besttennisapi.com)"
TIMEOUT = 10.0


def session(api_key: str = "", header: str = "X-API-Key") -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    if api_key:
        s.headers[header] = api_key
    return s


def time_endpoint(s: requests.Session, url: str, samples: int,
                  spacing_s: float) -> tuple[list[float], int, int, int]:
    """Sequential spaced GETs. Returns (elapsed_ms, ok, total, throttled).

    Spacing is not politeness theatre: probing faster than the published rate limit measures the
    rate limiter rather than the service, and distorts the very number you came for.
    """
    elapsed: list[float] = []
    ok = total = throttled = 0
    for _ in range(samples):
        total += 1
        t0 = time.perf_counter()
        try:
            r = s.get(url, timeout=TIMEOUT, allow_redirects=False)
        except Exception:  # noqa: BLE001 — a failed probe is data, not a crash
            time.sleep(spacing_s)
            continue
        dt = (time.perf_counter() - t0) * 1000.0
        if 200 <= r.status_code < 300:
            ok += 1
            elapsed.append(dt)          # timings for non-2xx are discarded: a fast 500 is not a fast read
        elif r.status_code == 429:
            throttled += 1
            time.sleep(max(spacing_s * 4, 5.0))
            continue
        time.sleep(spacing_s)
    return elapsed, ok, total, throttled
