"""Regional probe: one URL, timed from probes on several continents, appended to a CSV.

    python -m benchmark.regional probe --url https://api.example/v1/health --out probes.csv
    python -m benchmark.regional summarize probes.csv

GitHub-hosted runners cannot be placed in a chosen region, so the regional rows come from
Globalping (https://globalping.io), a free network of community-hosted probes with a public API.
Each run asks it for a few probes per continent. The probe's city, country and network are
recorded with every row, because a probe is a place on a network, not a whole continent.

The runner running this script also times the URL once and records that as its own row. Its
location is not known and is never guessed: the row says "github-runner" and nothing more,
apart from the CDN edge that answered (when the response names one).

No API key is sent anywhere. Point it only at URLs that need none.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import requests

from . import __version__
from .metrics import MIN_SAMPLE, percentile

GLOBALPING = "https://api.globalping.io/v1"
UA = f"tennis-api-benchmark/{__version__} regional (+https://github.com/livetennisapi/tennis-api-benchmark)"
CONTINENTS = ("EU", "NA", "SA", "AS", "OC", "AF")
POLL_SECONDS = 1.0       # Globalping allows 2 result reads per second per measurement
POLL_LIMIT_SECONDS = 60.0
TIMEOUT = 15.0

COLUMNS = (
    "measured_at", "source", "measurement_id", "continent", "country", "city", "asn", "network",
    "url", "status_code", "total_ms", "dns_ms", "tcp_ms", "tls_ms", "first_byte_ms",
    "download_ms", "edge", "error",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def edge_from_headers(headers: Mapping[str, Any]) -> str:
    """The CDN location code from a ``cf-ray`` header (``8a1b2c3d4e5f-FRA`` gives ``FRA``).

    Empty when there is no such header: an unknown edge stays unknown.
    """
    lowered = {str(k).lower(): v for k, v in headers.items()}
    ray = lowered.get("cf-ray")
    if isinstance(ray, list):
        ray = ray[0] if ray else None
    if not isinstance(ray, str) or "-" not in ray:
        return ""
    return ray.rsplit("-", 1)[1].strip().upper()


def measurement_request(url: str, per_continent: int) -> dict[str, Any]:
    """The Globalping request body for one HTTP GET of ``url`` from every continent."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) URL: {url!r}")
    request: dict[str, Any] = {"method": "GET", "path": parts.path or "/"}
    if parts.query:
        request["query"] = parts.query
    options: dict[str, Any] = {"protocol": "HTTPS" if parts.scheme == "https" else "HTTP", "request": request}
    if parts.port:
        options["port"] = parts.port
    return {
        "type": "http",
        "target": parts.hostname,
        "locations": [{"continent": c, "limit": per_continent} for c in CONTINENTS],
        "measurementOptions": options,
    }


def rows_from_measurement(body: Mapping[str, Any], url: str, measured_at: str) -> list[dict[str, Any]]:
    """One CSV row per probe in a finished Globalping measurement."""
    rows = []
    for item in body.get("results") or []:
        probe = item.get("probe") or {}
        result = item.get("result") or {}
        timings = result.get("timings") or {}
        status = result.get("status")
        error = "" if status == "finished" else f"probe status {status}"
        rows.append({
            "measured_at": measured_at,
            "source": "globalping",
            "measurement_id": body.get("id", ""),
            "continent": probe.get("continent", ""),
            "country": probe.get("country", ""),
            "city": probe.get("city", ""),
            "asn": probe.get("asn", ""),
            "network": probe.get("network", ""),
            "url": url,
            "status_code": result.get("statusCode", ""),
            "total_ms": timings.get("total", ""),
            "dns_ms": timings.get("dns", ""),
            "tcp_ms": timings.get("tcp", ""),
            "tls_ms": timings.get("tls", ""),
            "first_byte_ms": timings.get("firstByte", ""),
            "download_ms": timings.get("download", ""),
            "edge": edge_from_headers(result.get("headers") or {}),
            "error": error,
        })
    return rows


def globalping_rows(url: str, per_continent: int, http: requests.Session | None = None) -> list[dict[str, Any]]:
    s = http or requests.Session()
    s.headers.setdefault("User-Agent", UA)
    measured_at = _now()
    r = s.post(f"{GLOBALPING}/measurements", json=measurement_request(url, per_continent), timeout=TIMEOUT)
    if r.status_code == 429:
        raise RuntimeError("Globalping rate limit reached; no regional rows this run")
    r.raise_for_status()
    mid = r.json()["id"]

    deadline = time.monotonic() + POLL_LIMIT_SECONDS
    while True:
        time.sleep(POLL_SECONDS)
        body = s.get(f"{GLOBALPING}/measurements/{mid}", timeout=TIMEOUT).json()
        if body.get("status") != "in-progress" or time.monotonic() > deadline:
            break
    return rows_from_measurement(body, url, measured_at)


def runner_row(url: str) -> dict[str, Any]:
    """One GET from this machine on a fresh connection, so DNS, TCP and TLS are included,
    as they are in a Globalping HTTP test."""
    row = dict.fromkeys(COLUMNS, "")
    row.update(measured_at=_now(), source="github-runner" if os.environ.get("GITHUB_ACTIONS") else "local",
               url=url)
    with requests.Session() as s:
        s.headers["User-Agent"] = UA
        t0 = time.perf_counter()
        try:
            r = s.get(url, timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException as exc:
            row["error"] = type(exc).__name__
            return row
        row["total_ms"] = round((time.perf_counter() - t0) * 1000.0)
    row["status_code"] = r.status_code
    row["edge"] = edge_from_headers(r.headers)
    return row


def append(rows: Iterable[Mapping[str, Any]], path: str) -> int:
    rows = list(rows)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        if new:
            w.writeheader()
        for row in rows:
            w.writerow(row)
    return len(rows)


def summarize(path: str) -> list[dict[str, Any]]:
    """Per source and continent: clean sample count, and median and p90 only from 30 or more.

    A clean sample is a 2xx with a total time. Anything else is counted as not clean.
    """
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    other: dict[tuple[str, str], int] = defaultdict(int)
    first = last = ""
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["source"], row["continent"] or "-")
            first = first or row["measured_at"]
            last = row["measured_at"]
            ok = row["status_code"].isdigit() and 200 <= int(row["status_code"]) < 300 and row["total_ms"] != ""
            if ok:
                groups[key].append(float(row["total_ms"]))
            else:
                other[key] += 1
    out = []
    for key in sorted(set(groups) | set(other)):
        clean = groups.get(key, [])
        enough = len(clean) >= MIN_SAMPLE
        out.append({
            "source": key[0], "continent": key[1], "clean": len(clean), "not_clean": other.get(key, 0),
            "median_ms": percentile(clean, 50) if enough else None,
            "p90_ms": percentile(clean, 90) if enough else None,
            "from": first, "to": last,
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmark.regional", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="time one URL from every continent and append the rows")
    p.add_argument("--url", required=True, help="an http(s) URL that needs no key")
    p.add_argument("--out", required=True, help="CSV to append to")
    p.add_argument("--per-continent", type=int, default=2, help="Globalping probes per continent (default 2)")
    p.add_argument("--no-runner", action="store_true", help="skip the row timed from this machine")
    s = sub.add_parser("summarize", help="clean counts per continent, percentiles only from 30 or more")
    s.add_argument("csv")
    a = ap.parse_args(argv)

    if a.cmd == "summarize":
        for r in summarize(a.csv):
            figure = (f"median {r['median_ms']:,.0f} ms, p90 {r['p90_ms']:,.0f} ms" if r["median_ms"] is not None
                      else f"too few clean samples (needs {MIN_SAMPLE})")
            print(f"{r['source']:14} {r['continent']:3} clean={r['clean']:<6} not_clean={r['not_clean']:<5} {figure}")
        return 0

    if not 1 <= a.per_continent <= 8:
        ap.error("--per-continent must be 1 to 8 (Globalping allows 50 probes per anonymous measurement)")
    rows: list[dict[str, Any]] = []
    status = 0
    try:
        rows += globalping_rows(a.url, a.per_continent)
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        print(f"regional: no Globalping rows this run: {exc}", file=sys.stderr)
        status = 1
    if not a.no_runner:
        rows.append(runner_row(a.url))
    n = append(rows, a.out)
    print(f"regional: appended {n} rows to {a.out}", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
