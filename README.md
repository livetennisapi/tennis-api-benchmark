# tennis-api-benchmark

Measure any tennis API against a published, reproducible method — and get told when your sample
is too small to support a number.

This is the tool behind the figures on [besttennisapi.com](https://besttennisapi.com). It is
maintained by JSB Holdings LLC, which also operates Live Tennis API. It has no idea which
provider you point it at, which is the only reason its output about ours is worth anything.

## Install

```bash
git clone https://gitlab.com/livetennisapi/tennis-api-benchmark.git
cd tennis-api-benchmark
pip install -r requirements.txt
```

## Use

```bash
python -m benchmark \
  --base-url https://api.example/v1 \
  --api-key "$KEY" \
  --vantage "Frankfurt, cloud" \
  --samples 40
```

`--vantage` is not decoration. A response-time figure is largely a statement about distance, and
one recorded without saying where it was measured from cannot be interpreted by anyone else.

## What it measures

| Metric | How | Needs |
|---|---|---|
| Response time | Sequential spaced GETs; median; non-2xx timings discarded | any key |
| Observed availability | Success share over the run; 429s excluded from the denominator | any key |

## What it refuses to do

- **Print a percentile from fewer than 30 clean samples.** It says "too few clean samples"
  instead. A p50 over nine observations is an anecdote with a decimal point.
- **Print an availability share from fewer than 500 clean probes.**
- **Count a 429 as downtime.** A rate-limit response is the service working as documented and
  telling you to slow down. Counting it as unavailability produces a false figure — we know,
  because an early version of this code did exactly that and reported 92% for a service that had
  been up the whole time.
- **Probe faster than you tell it to.** Below the provider's published rate limit you are
  measuring the limiter, not the API.

## What its numbers are not

They are what one machine saw from one place over a bounded window. They are not an uptime
commitment, not an SLA, and **not** the delay between a point being played on court and the data
reaching you — nothing this tool can reach observes the court. If a provider advertises that
number, ask them how they measured it.

## Checking a latency claim

Ask a provider for two timestamps on every pushed frame: when the event occurred, and when the
frame was published. Then:

- `published_at - timestamp` is the provider's own processing time.
- your receive clock `- published_at` is transport to you.

A feed carrying one timestamp cannot be checked from outside, whatever number it advertises.

## Disclosure

Published by JSB Holdings LLC, which operates Live Tennis API. This tool is not neutral
infrastructure maintained by a disinterested party, and we are not going to pretend otherwise.
What we can offer instead is that the method is written down, the arithmetic is in
`benchmark/metrics.py` with no network in it, and you can run it against us and against anyone
else on identical terms.

If you get a result that contradicts something published on besttennisapi.com, open an issue with
your JSON output. A figure we cannot reproduce is one we need to withdraw or explain.

MIT licensed.

## How to cite

[CITATION.cff](CITATION.cff) holds the citation details in the Citation File Format.
[codemeta.json](codemeta.json) carries the same facts for software archives and catalogues.
