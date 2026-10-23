import json

from colab_monitor.usage_log import UsageLog, downsample


def test_missing_file_reads_empty(tmp_path):
    assert UsageLog(str(tmp_path / "usage.jsonl")).read() == []


def test_append_and_read_back(tmp_path):
    log = UsageLog(str(tmp_path / "sub" / "usage.jsonl"))
    log.append({"balance": 10.0, "rate_per_hour": 1.5}, now=100.0)
    log.append({"balance": 9.0, "rate_per_hour": 2.0}, now=200.0)
    assert log.read() == [
        {"t": 100.0, "balance": 10.0, "rate": 1.5},
        {"t": 200.0, "balance": 9.0, "rate": 2.0},
    ]


def test_read_since_filters_old_samples(tmp_path):
    log = UsageLog(str(tmp_path / "usage.jsonl"))
    for t in (100.0, 200.0, 300.0):
        log.append({"balance": 1.0, "rate_per_hour": 0.0}, now=t)
    assert [p["t"] for p in log.read(since=150.0)] == [200.0, 300.0]


def test_skips_corrupt_lines(tmp_path):
    path = tmp_path / "usage.jsonl"
    path.write_text(
        json.dumps({"t": 1.0, "balance": 1.0, "rate": 0.0}) + "\nnot json\n" + json.dumps({"t": 2.0}) + "\n"
    )
    assert UsageLog(str(path)).read() == [{"t": 1.0, "balance": 1.0, "rate": 0.0}]


def test_prune_drops_samples_older_than_cutoff(tmp_path):
    log = UsageLog(str(tmp_path / "usage.jsonl"))
    for t in (100.0, 200.0, 300.0):
        log.append({"balance": 1.0, "rate_per_hour": 0.0}, now=t)
    log.prune(before=250.0)
    assert [p["t"] for p in log.read()] == [300.0]


def test_downsample_keeps_order_endpoints_and_cap():
    points = [{"t": float(i)} for i in range(1000)]
    out = downsample(points, 100)
    assert len(out) <= 100
    assert out[0]["t"] == 0.0
    assert out[-1]["t"] == 999.0
    assert [p["t"] for p in out] == sorted(p["t"] for p in out)


def test_downsample_leaves_small_series_alone():
    points = [{"t": 1.0}, {"t": 2.0}]
    assert downsample(points, 100) == points


def test_read_reuses_parsed_samples_until_the_file_changes(tmp_path, monkeypatch):
    log = UsageLog(str(tmp_path / "usage.jsonl"))
    log.append({"balance": 10.0, "rate_per_hour": 1.0}, now=100.0)
    assert len(log.read()) == 1
    opened = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda *a, **k: opened.append(a[0]) or real_open(*a, **k))
    assert len(log.read(since=50.0)) == 1
    assert opened == []  # served from the cache
    monkeypatch.undo()
    log.append({"balance": 9.0, "rate_per_hour": 1.0}, now=200.0)
    assert [p["t"] for p in log.read()] == [100.0, 200.0]
