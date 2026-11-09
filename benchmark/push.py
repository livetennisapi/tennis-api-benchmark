"""Push-feed processing latency: `published_at - timestamp` on every frame, as the method defines.

    LTA_API_KEY=... python -m benchmark.push --vantage "Region, network" --duration 1800 \
        --out results/YYYY-MM-DD-push-processing

This is written for a Centrifugo-style feed that hands out a token at GET /ws-token (Live Tennis
API does). The arithmetic is `metrics.latency`, the same floor and the same nearest-rank p50 as
the REST probe. Parsing is pure and tested in tests/test_push.py.

Three terms, kept apart (see metrics.py):
  processing  published_at - event timestamp. Both stamps are written by the provider.
  transport   our receive clock - published_at. Depends on our clock, so it is recorded, not
              headlined.
  neither     is the delay from a point being played. Nothing here observes the court.

The feed may hand out the same state more than once (same match, same sequence, later
published_at). Every frame counts, because that is what the method says. The first publication of
each (match, sequence) is summarised beside it so a reader can see how much the repeats move it.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metrics import MIN_SAMPLE, latency, percentile

MAX_DURATION_S = 90 * 60
LIVE_CHECK_EVERY_S = 300
METHOD = "https://besttennisapi.com/methodology#latency"
FIELDS = ("received_utc", "channel", "type", "match_id", "tour", "sequence",
          "event_ts", "published_at", "processing_ms", "transport_ms")


def parse_ts(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def stamps(frame: dict[str, Any]) -> tuple[str, Any, Any, str | None, str | None] | None:
    """(type, match_id, sequence, event_ts, published_at) for a frame that has an event stamp.

    Score frames carry the event stamp at score.timestamp, point frames at point.ts (capture
    time). published_at sits at the top of both. Anything else returns None.
    """
    t = frame.get("type")
    pub = frame.get("published_at")
    if t == "score" and isinstance(frame.get("score"), dict):
        s = frame["score"]
        return t, frame.get("match_id"), s.get("sequence"), s.get("timestamp"), pub
    if t == "point" and isinstance(frame.get("point"), dict):
        p = frame["point"]
        return t, frame.get("match_id"), p.get("seq"), p.get("ts"), pub
    return None


def delta_ms(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds() * 1000.0


def split_batch(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def spread(values: list[float]) -> dict[str, float] | None:
    clean = [v for v in values if v is not None and v >= 0]
    if not clean:
        return None
    return {p: round(percentile(clean, q), 1)
            for p, q in (("p10", 10), ("p25", 25), ("p50", 50), ("p75", 75), ("p90", 90),
                         ("p99", 99))} | {"min": round(min(clean), 1), "max": round(max(clean), 1)}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure: rows as written to frames.csv -> the summary. A negative processing delta means the
    two stamps disagree in the wrong direction; it is dropped, never clamped to zero."""
    out: dict[str, Any] = {"min_sample": MIN_SAMPLE}
    for kind in ("score", "point"):
        mine = [r for r in rows if r["type"] == kind]
        proc = [r["processing_ms"] for r in mine if r["processing_ms"] is not None]
        neg = sum(1 for v in proc if v < 0)
        first: dict[tuple, float] = {}
        for r in mine:
            k = (r["match_id"], r["sequence"])
            if r["processing_ms"] is not None and k not in first and r["sequence"] is not None:
                first[k] = r["processing_ms"]
        m_all = latency(proc, f"processing_ms_{kind}", METHOD)
        m_first = latency(list(first.values()), f"processing_ms_{kind}_first_publication", METHOD)
        trans = [r["transport_ms"] for r in mine if r["transport_ms"] is not None]
        out[kind] = {
            "frames": len(mine),
            "frames_with_both_stamps": len(proc),
            "dropped_negative": neg,
            "clean": len([v for v in proc if v >= 0]),
            "matches": len({r["match_id"] for r in mine}),
            "processing_p50_ms": m_all.value if m_all else None,
            "processing_spread_ms": spread(proc),
            "first_publication": {
                "states": len(first),
                "clean": len([v for v in first.values() if v >= 0]),
                "processing_p50_ms": m_first.value if m_first else None,
                "processing_spread_ms": spread(list(first.values())),
            },
            "transport_spread_ms_not_published": spread(trans),
        }
    return out


async def collect(key: str, out: Path, duration: float, vantage: str, base: str) -> None:
    import requests
    import websockets

    out.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"vantage": vantage, "base_url": base, "method": METHOD,
                            "duration_requested_s": duration, "live_checks": [],
                            "reconnects": 0, "channels": ["slate:all", "point:slate"]}
    rows: list[dict[str, Any]] = []
    headers = {"X-API-Key": key}
    stop_at = time.monotonic() + duration
    next_live = 0.0
    started = datetime.now(timezone.utc)

    s = requests.Session()
    s.headers.update({"User-Agent": "tennis-api-benchmark/0.1 (+https://besttennisapi.com)", **headers})

    def get(path: str, **params: str) -> Any:
        r = s.get(f"{base}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    try:
        async def live_check() -> int:
            body = await asyncio.to_thread(get, "/matches", status="live")
            data = body.get("data", [])
            tours: dict[str, int] = {}
            for m in data:
                tours[str(m.get("tour"))] = tours.get(str(m.get("tour")), 0) + 1
            meta["live_checks"].append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                        "live": len(data), "by_tour": tours})
            print(f"live check: {len(data)} live {tours}", file=sys.stderr)
            return len(data)

        tours_by_match: dict[Any, str] = {}
        attempts = 0
        while time.monotonic() < stop_at:
            if time.monotonic() >= next_live:
                next_live = time.monotonic() + LIVE_CHECK_EVERY_S
                if await live_check() == 0:
                    meta["stopped"] = "no live play"
                    break
            try:
                tok = await asyncio.to_thread(get, "/ws-token")
                async with websockets.connect(tok["ws_url"], max_size=None) as ws:
                    await ws.send(json.dumps({"connect": {"token": tok["token"]}, "id": 1}))
                    for i, ch in enumerate(meta["channels"], start=2):
                        await ws.send(json.dumps({"subscribe": {"channel": ch}, "id": i}))
                    while time.monotonic() < stop_at and time.monotonic() < next_live:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        except asyncio.TimeoutError:
                            continue
                        recv = datetime.now(timezone.utc)  # stamped before parsing
                        for msg in split_batch(str(raw)):
                            if msg == {}:
                                await ws.send("{}")
                                continue
                            push = msg.get("push") or {}
                            d = (push.get("pub") or {}).get("data")
                            if not isinstance(d, dict):
                                continue
                            if d.get("tour"):
                                tours_by_match[d.get("match_id")] = d["tour"]
                            st = stamps(d)
                            if st is None:
                                continue
                            t, mid, seq, ets, pub = st
                            pub_dt, ets_dt = parse_ts(pub), parse_ts(ets)
                            proc = delta_ms(pub_dt, ets_dt)
                            trans = delta_ms(recv, pub_dt)
                            rows.append({
                                "received_utc": recv.isoformat(timespec="milliseconds"),
                                "channel": push.get("channel", "").split(":")[0],
                                "type": t, "match_id": mid,
                                "tour": tours_by_match.get(mid, ""), "sequence": seq,
                                "event_ts": ets, "published_at": pub,
                                "processing_ms": None if proc is None else round(proc, 3),
                                "transport_ms": None if trans is None else round(trans, 3),
                            })
                attempts = 0
            except (OSError, websockets.WebSocketException, requests.RequestException) as exc:
                attempts += 1
                meta["reconnects"] += 1
                print(f"feed error ({type(exc).__name__}); reconnect {attempts}", file=sys.stderr)
                if attempts > 5:
                    meta["stopped"] = f"gave up after {attempts} failed connects"
                    break
                await asyncio.sleep(5)
        if "stopped" not in meta:
            await live_check()
    except Exception as exc:  # noqa: BLE001 — keep what was collected
        meta["stopped"] = f"aborted: {type(exc).__name__}"
    finally:
        s.close()

    ended = datetime.now(timezone.utc)
    meta["window_utc"] = [started.isoformat(timespec="seconds"), ended.isoformat(timespec="seconds")]
    with (out / "frames.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    summary = {"generated_at": ended.isoformat(timespec="seconds").replace("+00:00", "Z"),
               "run": meta, "summary": summarise(rows),
               "note": ("Processing time inside the provider, from two provider stamps. Not the "
                        "delay between a point being played and the data reaching anyone.")}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["summary"], indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmark.push", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="https://api.livetennisapi.com/api/public/v1")
    ap.add_argument("--vantage", required=True)
    ap.add_argument("--duration", type=float, default=1800)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    key = os.environ.get("LTA_API_KEY", "")
    if not key:
        print("LTA_API_KEY is not set", file=sys.stderr)
        return 2
    if not 0 < a.duration <= MAX_DURATION_S:
        print(f"--duration must be in (0, {MAX_DURATION_S}]", file=sys.stderr)
        return 2
    asyncio.run(collect(key, Path(a.out), a.duration, a.vantage, a.base_url.rstrip("/")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
