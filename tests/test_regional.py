"""The regional probe's parsing and arithmetic, checked without a network.

The Globalping body below is shaped like a finished HTTP measurement in its published OpenAPI
spec (https://api.globalping.io/v1/spec.yaml). The places and timings are made up for the test.
"""
import csv

import pytest

from benchmark import regional

FINISHED = {
    "id": "testMeasurement01",
    "type": "http",
    "status": "finished",
    "probesCount": 2,
    "results": [
        {
            "probe": {"continent": "EU", "country": "XX", "city": "Testville", "asn": 64500,
                      "network": "Example Net", "state": None, "region": "Western Europe",
                      "latitude": 0.0, "longitude": 0.0, "tags": [], "resolvers": []},
            "result": {"status": "finished", "statusCode": 200, "statusCodeName": "OK",
                       "headers": {"cf-ray": "0123456789abcdef-AMS", "content-type": "application/json"},
                       "rawHeaders": "", "rawBody": "{}", "rawOutput": "", "truncated": False,
                       "resolvedAddress": "192.0.2.1", "tls": None,
                       "timings": {"total": 120, "dns": 10, "tcp": 5, "tls": 20, "firstByte": 80,
                                   "download": 5}},
        },
        {
            "probe": {"continent": "AF", "country": "YY", "city": "Sampletown", "asn": 64501,
                      "network": "Other Net", "state": None, "region": "Western Africa",
                      "latitude": 0.0, "longitude": 0.0, "tags": [], "resolvers": []},
            "result": {"status": "failed", "rawOutput": "connect ETIMEDOUT"},
        },
    ],
}


def test_request_body_covers_every_continent_with_the_path_and_query():
    body = regional.measurement_request("https://api.example/v1/health?x=1", 2)
    assert body["type"] == "http"
    assert body["target"] == "api.example"
    assert [loc["continent"] for loc in body["locations"]] == list(regional.CONTINENTS)
    assert all(loc["limit"] == 2 for loc in body["locations"])
    opts = body["measurementOptions"]
    assert opts["protocol"] == "HTTPS"
    assert opts["request"] == {"method": "GET", "path": "/v1/health", "query": "x=1"}


def test_request_body_refuses_a_non_http_url():
    with pytest.raises(ValueError):
        regional.measurement_request("ftp://example/health", 1)


def test_edge_is_read_from_cf_ray_and_left_blank_otherwise():
    assert regional.edge_from_headers({"CF-Ray": "abc-fra"}) == "FRA"
    assert regional.edge_from_headers({"cf-ray": ["abc-SIN"]}) == "SIN"
    assert regional.edge_from_headers({"server": "x"}) == ""


def test_rows_keep_the_probe_place_and_mark_failures():
    rows = regional.rows_from_measurement(FINISHED, "https://api.example/v1/health", "2026-01-01T00:00:00Z")
    ok, failed = rows
    assert ok["continent"] == "EU" and ok["city"] == "Testville" and ok["network"] == "Example Net"
    assert ok["total_ms"] == 120 and ok["first_byte_ms"] == 80 and ok["edge"] == "AMS"
    assert ok["error"] == ""
    assert failed["total_ms"] == "" and failed["status_code"] == ""
    assert failed["error"] == "probe status failed"


def test_append_writes_the_header_once(tmp_path):
    out = tmp_path / "probes.csv"
    rows = regional.rows_from_measurement(FINISHED, "u", "2026-01-01T00:00:00Z")
    regional.append(rows, str(out))
    regional.append(rows, str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(regional.COLUMNS)
    assert len(lines) == 5


def _write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=regional.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({**dict.fromkeys(regional.COLUMNS, ""), **r})


def test_summary_refuses_a_percentile_below_the_floor(tmp_path):
    out = tmp_path / "p.csv"
    rows = [{"measured_at": "t", "source": "globalping", "continent": "EU", "status_code": "200",
             "total_ms": str(100 + i)} for i in range(29)]
    _write(out, rows)
    (eu,) = regional.summarize(str(out))
    assert eu["clean"] == 29 and eu["median_ms"] is None


def test_summary_excludes_non_2xx_and_failed_probes(tmp_path):
    out = tmp_path / "p.csv"
    rows = [{"measured_at": "t", "source": "globalping", "continent": "EU", "status_code": "200",
             "total_ms": str(i)} for i in range(1, 31)]
    rows += [{"measured_at": "t", "source": "globalping", "continent": "EU", "status_code": "503",
              "total_ms": "5"},
             {"measured_at": "t", "source": "globalping", "continent": "EU", "error": "probe status failed"}]
    _write(out, rows)
    (eu,) = regional.summarize(str(out))
    assert eu["clean"] == 30 and eu["not_clean"] == 2
    assert eu["median_ms"] == 15.0 and eu["p90_ms"] == 27.0
