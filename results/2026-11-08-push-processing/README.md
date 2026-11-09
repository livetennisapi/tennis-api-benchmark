# Push processing latency, 8 November 2026

Live Tennis API push feed, 17:14:50 to 17:44:52 UTC on 8 November 2026. The window was fixed at 30
minutes before the run started.

**Median processing latency: 168 ms over 1,565 score frames** (p90 610 ms) from 27 live matches.

Processing latency is `published_at` minus the frame's event timestamp. Both stamps are written by
the provider, so this is time inside its pipeline. It is not the delay between a point being
played and the data reaching you. Nothing in this run observes the court.

## How it was run

```bash
LTA_API_KEY=... python -m benchmark.push --vantage "Germany, Hetzner network" \
  --duration 1800 --out results/2026-11-08-push-processing
```

One websocket connection, subscribed to `slate:all` and `point:slate`. No reconnects. A live
matches check ran every five minutes and found 19 to 26 matches live (Challenger, ITF, ATP
Stockholm and UTR events). Arithmetic is `benchmark/metrics.py`: nearest-rank median, nothing
reported below 30 clean samples, negative deltas dropped. None were negative.

## Results

| Frames | Event stamp | n | Median | p25 to p75 | p90 | p99 | Range |
|---|---|---|---|---|---|---|---|
| Score frames, every frame | `score.timestamp` | 1,565 | 168 ms | 88 to 310 ms | 610 ms | 1,396 ms | 14 to 2,098 ms |
| Score frames, first publication of each state | `score.timestamp` | 799 | 100 ms | 55 to 194 ms | 388 ms | 1,036 ms | 14 to 1,562 ms |
| Point frames | `point.ts` (capture time) | 624 | 43 ms | 22 to 96 ms | 255 ms | 645 ms | 2 to 22,182 ms |

The headline is the first row, because the method counts every frame. The feed publishes some
score states more than once, with the same sequence and a later `published_at`. The second row
keeps only the first frame per match and sequence, so you can see what the repeats add.

Score frames by tour, every frame:

| Tour | n | Median | p90 |
|---|---|---|---|
| Challenger | 700 | 181 ms | 663 ms |
| ITF | 547 | 161 ms | 526 ms |
| No tour field (UTR events) | 259 | 144 ms | 614 ms |
| ATP | 59 | 179 ms | 770 ms |

## What is not here

Transport (our receive clock minus `published_at`) is recorded in `frames.csv` but not
headlined. It depends on this host's clock and its network path. The host was NTP-synchronised,
and the median was 54 ms for score frames.

One machine, one 30-minute window, one evening of lower-tier play. This is a single run, not
an SLA.

## Files

- `frames.csv`: one row per frame. Match id, tour, sequence, both stamps, our receive time and
  the two deltas. No scores or prices.
- `summary.json`: the run metadata, every live check and the summary above.
