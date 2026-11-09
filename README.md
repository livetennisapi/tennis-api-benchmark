# Regional probe data

`probes.csv` gets one batch of rows an hour from the `regional-probe` workflow on `main`. Each batch is 12 Globalping probes, two on each of six continents, and one row timed from the GitHub runner.

These are raw rows, not a result. [The method README on main](https://github.com/livetennisapi/tennis-api-benchmark/blob/main/results/regional-probe/README.md) explains the columns and what the numbers do not mean. No figure is published from this file before about 30 days of rows exist.
