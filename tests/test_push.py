"""Push-feed parsing and summary, checked without a network. Frame shapes as observed on
2026-11-08: published_at at the top, the event stamp at score.timestamp or point.ts."""
from benchmark.push import delta_ms, parse_ts, stamps, summarise

SCORE = {"type": "score", "match_id": 7, "tour": "challenger", "published_at": "2026-11-08T17:11:19.809Z",
         "score": {"sequence": 107, "timestamp": "2026-11-08T17:11:19.093712Z"}}
POINT = {"type": "point", "match_id": 7, "published_at": "2026-11-08T17:11:20.120Z",
         "point": {"seq": 65, "ts": "2026-11-08T17:11:19.715068Z"}}


def test_score_frame_stamps():
    t, mid, seq, ets, pub = stamps(SCORE)
    assert (t, mid, seq) == ("score", 7, 107)
    assert round(delta_ms(parse_ts(pub), parse_ts(ets)), 3) == 715.288


def test_point_frame_stamps():
    t, _, seq, ets, pub = stamps(POINT)
    assert (t, seq) == ("point", 65)
    assert round(delta_ms(parse_ts(pub), parse_ts(ets)), 3) == 404.932


def test_frames_without_an_event_stamp_are_ignored():
    assert stamps({"type": "point_update", "published_at": "2026-11-08T17:11:39.300Z"}) is None
    assert parse_ts(None) is None
    assert parse_ts("2026-11-08T17:11:19") is None  # no zone, no comparison


def _row(seq, ms, kind="score", mid=1):
    return {"type": kind, "match_id": mid, "sequence": seq, "processing_ms": ms, "transport_ms": 50.0}


def test_summary_refuses_below_thirty_clean_samples():
    rows = [_row(i, 100.0) for i in range(29)] + [_row(99, -5.0)]
    s = summarise(rows)["score"]
    assert s["clean"] == 29 and s["dropped_negative"] == 1
    assert s["processing_p50_ms"] is None


def test_summary_counts_every_frame_and_reports_first_publication_beside_it():
    rows = [_row(i, 100.0) for i in range(30)] + [_row(i, 900.0) for i in range(30)]
    s = summarise(rows)["score"]
    assert s["clean"] == 60
    assert s["processing_p50_ms"] == "100"  # nearest rank: the 30th of 60
    assert s["first_publication"]["states"] == 30
    assert s["first_publication"]["processing_p50_ms"] == "100"
    assert s["processing_spread_ms"]["p90"] == 900.0
