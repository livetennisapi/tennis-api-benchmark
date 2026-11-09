# Regional response time (collecting, no figures yet)

This folder holds the method. The data goes to [`probes.csv` on the `regional-probe-data` branch](https://github.com/livetennisapi/tennis-api-benchmark/blob/regional-probe-data/probes.csv), one append an hour, so the hourly commits stay out of `main`.

There are no figures here, and none will be published before about 30 days of rows exist. The summary command refuses to print a median for any continent with fewer than 30 clean samples (`MIN_SAMPLE` in `benchmark/metrics.py`).

## What is measured

The target is `GET https://api.livetennisapi.com/api/public/v1/health`. The OpenAPI spec lists it as the liveness probe, and it needs no key. The probe sends no key, so it counts against nobody's quota. Its body is two short fields, so its time is mostly network, TLS and the trip to the origin. It says little about how long a data endpoint takes to build its answer.

Each row is one HTTP GET on a new connection, so DNS, TCP and TLS are included. The columns:

| Column | Meaning |
|---|---|
| `measured_at` | UTC time the measurement was requested |
| `source` | `globalping` or `github-runner` |
| `measurement_id` | Globalping's id for the measurement, so a row can be traced |
| `continent`, `country`, `city`, `asn`, `network` | Where the Globalping probe is, as Globalping reports it |
| `status_code` | HTTP status. Rows that are not 2xx are kept but never timed |
| `total_ms` | Whole request time |
| `dns_ms`, `tcp_ms`, `tls_ms`, `first_byte_ms`, `download_ms` | Globalping's split of `total_ms`. Empty for runner rows |
| `edge` | The CDN location that answered, from the `cf-ray` header. Empty if the header is missing |
| `error` | Why a probe gave no time, if it gave none |

## Where the probes are, and why GitHub runners are not enough

GitHub-hosted runners cannot be placed in a region. GitHub's documentation says standard Linux runners run on Azure or AWS and offers no region choice. Larger runners need a Team or Enterprise Cloud plan and are billed by the minute. So the regional rows come from [Globalping](https://globalping.io), a network of probes around the world. Its API is free and needs no account.

Each hourly run asks Globalping for two probes on each of six continents: Europe, North America, South America, Asia, Oceania and Africa. That is 12 tests an hour, inside its anonymous limit of 250 tests an hour.

The runner that runs the workflow also times the URL once. Its location is unknown, so its row says `github-runner` and gives no place. The `edge` column still shows which CDN location answered it.

## What these numbers will not be

- A continent figure is not the continent. It is the probes Globalping picked, each in one city on one network. Read `city` and `network` before quoting a continent median.
- Probes change between runs. The same continent is sampled from different places over the month, which is the point, but it adds spread.
- This is the time to a CDN edge and on to the API's origin and back. It is not the delay between a point being played and the data reaching you. Nothing here observes the court.
- Globalping's own timing is what its probe reports. We have not checked their clocks.

## Running it yourself

```bash
pip install -r requirements.txt
python -m benchmark.regional probe --url https://api.livetennisapi.com/api/public/v1/health --out probes.csv
python -m benchmark.regional summarize probes.csv
```

`probe` works against any URL that needs no key. Never pass a key to it: Globalping probes are third-party machines.

## Costs

Nothing. Actions minutes are free in a public repository, and Globalping's anonymous API is free within its limits. GitHub disables scheduled workflows in a public repository after 60 days without activity. If the hourly commits stop, check that first.
