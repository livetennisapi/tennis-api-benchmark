"""CLI: point it at any tennis API and print the same metric set besttennisapi.com publishes.

    python -m benchmark --base-url https://api.example/v1 --api-key "$KEY" --samples 40

It refuses to print a percentile from too small a sample, and prints "not measured" instead.
That is the point: a benchmark that always produces a number is not measuring anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import __version__
from .metrics import Metric, availability, latency
from .probe import session, time_endpoint

# Paths are supplied by the caller because providers do not agree on them. The defaults match the
# shape most tennis APIs expose; override with --path for anything else.
DEFAULT_PATHS = ["/health", "/matches?status=live", "/fixtures"]
METHOD = "https://besttennisapi.com/methodology"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmark", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True, help="provider base URL, no trailing slash")
    ap.add_argument("--api-key", default="", help="your key for THAT provider")
    ap.add_argument("--key-header", default="X-API-Key", help="auth header name (default X-API-Key)")
    ap.add_argument("--path", action="append", dest="paths",
                    help="endpoint path to probe; repeatable. Defaults to a common set.")
    ap.add_argument("--samples", type=int, default=40, help="probes per endpoint (default 40)")
    ap.add_argument("--spacing", type=float, default=1.0,
                    help="seconds between probes (default 1.0). Do not lower this below the "
                         "provider's published rate limit or you will measure the limiter.")
    ap.add_argument("--vantage", default="",
                    help="where you are running from. Recorded with the result; a latency figure "
                         "without one cannot be interpreted.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    a = ap.parse_args(argv)

    base = a.base_url.rstrip("/")
    paths = a.paths or DEFAULT_PATHS
    s = session(a.api_key, a.key_header)

    metrics: list[Metric] = []
    ok_t = tot_t = thr_t = 0
    for path in paths:
        elapsed, ok, total, thr = time_endpoint(s, base + path, a.samples, a.spacing)
        ok_t += ok
        tot_t += total
        thr_t += thr
        key = "response_ms_" + path.strip("/").split("?")[0].replace("/", "_") or "root"
        m = latency(elapsed, key, f"{METHOD}#response-time",
                    caveats=(f"Sequential spaced GETs of {path} from one location. "
                             "Timings for non-2xx responses are discarded.",))
        if m:
            metrics.append(m)
        else:
            print(f"note: {path} produced too few clean samples to report a percentile",
                  file=sys.stderr)

    av = availability(ok_t, tot_t, thr_t, f"{METHOD}#availability")
    if av:
        metrics.append(av)
    else:
        print(f"note: {tot_t - thr_t} clean probes is below the floor for an availability share",
              file=sys.stderr)

    now = datetime.now(timezone.utc)
    out = {
        "harness_version": __version__,
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "base_url": base,
        "vantage": a.vantage or "undeclared",
        "note": ("Measured from one vantage point. Not a comparison with any other provider, and "
                 "not the delay between a point being played and the data arriving."),
        "metrics": {m.key: {"value": m.value, "unit": m.unit, "n": m.n,
                            "method": m.method, "caveats": list(m.caveats)} for m in metrics},
    }
    if a.json:
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    print(f"\ntennis-api-benchmark {__version__}  ·  {base}")
    print(f"vantage: {out['vantage']}  ·  {out['generated_at']}\n")
    if not metrics:
        print("  no metric cleared its minimum sample size — nothing to report.")
    for m in metrics:
        print(f"  {m.key:34} {m.value:>10} {m.unit:<3} n={m.n}")
    print(f"\n  {out['note']}")
    if not a.vantage:
        print("  WARNING: no --vantage given, so these figures cannot be interpreted by anyone else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
