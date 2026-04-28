import contextlib
import datetime as dt
import decimal
import json
import os
import shutil
import urllib.error

import pytest

from converter import currency


def test_parse_currency_query_variants():
    assert currency.parse_query("2000 isk eur") == currency.CurrencyQuery(
        amount=decimal.Decimal("2000"),
        source="isk",
        target="eur",
    )
    assert currency.parse_query("2000 isk to eur") == currency.CurrencyQuery(
        amount=decimal.Decimal("2000"),
        source="isk",
        target="eur",
    )
    assert currency.parse_query("2000 isk in eur") == currency.CurrencyQuery(
        amount=decimal.Decimal("2000"),
        source="isk",
        target="eur",
    )
    assert currency.parse_query("2000 xpf eur") == currency.CurrencyQuery(
        amount=decimal.Decimal("2000"),
        source="xpf",
        target="eur",
    )
    assert currency.parse_query("1,5 usd eur") == currency.CurrencyQuery(
        amount=decimal.Decimal("1.5"),
        source="usd",
        target="eur",
    )


def test_parse_currency_query_rejects_grouped_amounts():
    assert currency.parse_query("1,000 usd eur") is None
    assert currency.parse_query("1,000.50 usd eur") is None


def test_parse_currency_query_rejects_regular_units():
    assert currency.parse_query("100 cup tsp") is None
    assert currency.parse_query("100 psi bar") is None
    assert currency.parse_query("100 btu cal") is None
    assert currency.parse_query("100 ozm lbm") is None
    assert currency.parse_query("10 m in cm") is None
    assert currency.parse_query("1 + 1") is None


def test_cache_round_trip(tmp_path):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )

    currency.write_rate_cache(tmp_path, cache)
    loaded = currency.read_rate_cache(tmp_path, "isk")

    assert loaded == cache


def test_rate_cache_freshness_accepts_same_day_or_newer():
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )

    assert cache.is_fresh(dt.date(2026, 4, 25))
    assert not cache.is_fresh(dt.date(2026, 4, 26))


def test_rate_cache_freshness_defaults_to_today():
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )

    assert cache.is_fresh()


def test_rate_cache_path_rejects_invalid_base(tmp_path):
    with pytest.raises(ValueError):
        currency.rate_cache_path(tmp_path, "../usd")


def test_read_rate_cache_invalid_base_returns_none(tmp_path):
    assert currency.read_rate_cache(tmp_path, "../usd") is None


def test_normalize_base_rejects_non_string():
    with pytest.raises(ValueError):
        currency.normalize_base(None)


def test_write_rate_cache_rejects_invalid_base(tmp_path):
    cache = currency.RateCache(
        base="../usd",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )

    with pytest.raises(ValueError):
        currency.write_rate_cache(tmp_path, cache)


def test_read_rate_cache_rejects_base_mismatch(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()
    (rate_dir / "usd.json").write_text(
        json.dumps(
            {
                "base": "eur",
                "date": "2026-04-24",
                "fetched_at": "2026-04-25",
                "rates": {"usd": "1.14052"},
            }
        ),
        encoding="utf-8",
    )

    assert currency.read_rate_cache(tmp_path, "usd") is None


def test_read_rate_cache_rejects_non_mapping_rates(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()

    for rates in ([], None):
        (rate_dir / "usd.json").write_text(
            json.dumps(
                {
                    "base": "usd",
                    "date": "2026-04-24",
                    "fetched_at": "2026-04-25",
                    "rates": rates,
                }
            ),
            encoding="utf-8",
        )

        assert currency.read_rate_cache(tmp_path, "usd") is None


def test_read_rate_cache_rejects_non_finite_rates(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()

    for rate in ("NaN", "Infinity", "-Infinity"):
        (rate_dir / "usd.json").write_text(
            json.dumps(
                {
                    "base": "usd",
                    "date": "2026-04-24",
                    "fetched_at": "2026-04-25",
                    "rates": {"eur": rate},
                }
            ),
            encoding="utf-8",
        )

        assert currency.read_rate_cache(tmp_path, "usd") is None


def test_write_rate_cache_does_not_use_fixed_tmp_path(tmp_path):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )

    currency.write_rate_cache(tmp_path, cache)

    assert not (tmp_path / "currency" / "isk.json.tmp").exists()


def test_write_rate_cache_removes_unique_tmp_path_on_failure(
    tmp_path, monkeypatch
):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )

    def fail_replace(tmp_path, path):
        raise OSError("replace failed")

    monkeypatch.setattr(currency.os, "replace", fail_replace)

    with pytest.raises(OSError):
        currency.write_rate_cache(tmp_path, cache)

    assert list((tmp_path / "currency").glob("*.tmp")) == []


def test_corrupt_cache_returns_none(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()
    (rate_dir / "isk.json").write_text("{not-json", encoding="utf-8")

    assert currency.read_rate_cache(tmp_path, "isk") is None


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def lock_metadata_path(lock_dir, token):
    try:
        return lock_dir.__class__(currency._metadata_path(lock_dir, token))
    except TypeError:
        return lock_dir.__class__(currency._metadata_path(lock_dir))


def write_lock_metadata(lock_dir, token, created_at=None):
    created_at = created_at or dt.datetime.now(dt.timezone.utc)
    lock_metadata_path(lock_dir, token).write_text(
        json.dumps({
            "created_at": created_at.isoformat(),
            "token": token,
        }),
        encoding="utf-8",
    )


def read_lock_metadata(lock_dir):
    metadata_files = list(lock_dir.glob("metadata*.json"))
    assert len(metadata_files) == 1
    return json.loads(metadata_files[0].read_text(encoding="utf-8"))


def test_fetch_rates_uses_primary_url(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse({
            "date": "2026-04-24",
            "isk": {"eur": 0.0069542179},
        })

    monkeypatch.setattr(currency.urllib.request, "urlopen", fake_urlopen)

    cache = currency.fetch_rates("isk")

    assert calls == [
        "https://cdn.jsdelivr.net/npm/"
        "@fawazahmed0/currency-api@latest/v1/currencies/isk.json"
    ]
    assert cache.rates["eur"] == decimal.Decimal("0.0069542179")


def test_fetch_rates_uses_fallback_after_primary_failure(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise urllib.error.URLError("down")
        return FakeResponse({
            "date": "2026-04-24",
            "isk": {"eur": 0.0069542179},
        })

    monkeypatch.setattr(currency.urllib.request, "urlopen", fake_urlopen)

    cache = currency.fetch_rates("isk")

    assert calls[1] == (
        "https://latest.currency-api.pages.dev/v1/currencies/isk.json"
    )
    assert cache.base == "isk"


def test_fetch_rates_uses_fallback_after_malformed_primary(monkeypatch):
    calls = []
    payloads = [
        {"date": "2026-04-24", "usd": {"eur": 1}},
        {"date": "2026-04-24", "isk": {"eur": 0.0069542179}},
    ]

    def fake_load_json_url(url):
        calls.append(url)
        return payloads.pop(0)

    monkeypatch.setattr(currency, "_load_json_url", fake_load_json_url)

    cache = currency.fetch_rates("isk")

    assert len(calls) == 2
    assert cache.rates["eur"] == decimal.Decimal("0.0069542179")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"date": "not-a-date", "isk": {"eur": 1}},
        {"date": "2026-04-24", "isk": []},
        {"date": "2026-04-24", "isk": {"eur": "NaN"}},
    ],
)
def test_fetch_rates_rejects_malformed_provider_payloads(
    payload, monkeypatch
):
    monkeypatch.setattr(currency, "_load_json_url", lambda url: payload)

    with pytest.raises(RuntimeError, match="Unable to fetch rates for isk"):
        currency.fetch_rates("isk")


def test_lock_prevents_stampede(tmp_path):
    first = currency.acquire_refresh_lock(tmp_path, "isk")
    second = currency.acquire_refresh_lock(tmp_path, "isk")

    assert first.acquired is True
    assert second.acquired is False

    first.release()
    third = currency.acquire_refresh_lock(tmp_path, "isk")

    assert third.acquired is True
    third.release()


def test_lock_none_stale_after_uses_default_without_bypassing_lock(tmp_path):
    first = currency.acquire_refresh_lock(tmp_path, "isk")
    second = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=None,
    )

    assert first.acquired is True
    assert second.acquired is False

    first.release()


def test_lock_zero_stale_after_honored_for_immediate_recovery(tmp_path):
    first = currency.acquire_refresh_lock(tmp_path, "isk")
    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(0),
    )

    assert first.acquired is True
    assert recovered.acquired is True

    recovered.release()


def test_stale_lock_can_be_recovered(tmp_path, monkeypatch):
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    assert lock.acquired is True

    stale_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    write_lock_metadata(lock_dir, lock.token, created_at=stale_time)

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is True
    recovered.release()


def test_fresh_lock_directory_without_metadata_is_not_stolen(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)

    lock = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert lock.acquired is False


def test_fresh_malformed_lock_metadata_is_not_stolen(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "metadata.json").write_text("{not-json", encoding="utf-8")

    lock = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert lock.acquired is False


def test_fresh_lock_metadata_with_invalid_token_is_not_stolen(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    lock_metadata_path(lock_dir, "f" * 32).write_text(
        json.dumps({
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "token": "",
        }),
        encoding="utf-8",
    )

    lock = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert lock.acquired is False


def test_old_lock_directory_without_metadata_can_be_recovered(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    old_time = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    ).timestamp()
    os.utime(lock_dir, (old_time, old_time))

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is True
    recovered.release()


def test_lock_vanishing_during_stale_check_can_be_acquired(
    tmp_path, monkeypatch
):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "metadata.json").write_text("{not-json", encoding="utf-8")

    def vanish_during_getmtime(path):
        shutil.rmtree(lock_dir)
        raise FileNotFoundError(path)

    monkeypatch.setattr(
        currency.os.path,
        "getmtime",
        vanish_during_getmtime,
    )

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is True
    recovered.release()


def test_failed_metadata_write_removes_new_lock_directory(
    tmp_path, monkeypatch
):
    def fail_metadata_write(path, token):
        raise OSError("metadata failed")

    monkeypatch.setattr(currency, "_write_lock_metadata", fail_metadata_write)

    with pytest.raises(OSError, match="metadata failed"):
        currency.acquire_refresh_lock(tmp_path, "isk")

    assert not (tmp_path / "currency" / "locks" / "isk.lock").exists()


def test_lock_metadata_path_rejects_invalid_token(tmp_path):
    with pytest.raises(ValueError, match="invalid lock token"):
        currency._metadata_path(tmp_path, "not-a-token")


def test_lock_token_match_returns_false_for_malformed_metadata(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    token = "1" * 32
    lock_dir.mkdir(parents=True)
    lock_metadata_path(lock_dir, token).write_text(
        "{not-json",
        encoding="utf-8",
    )

    assert not currency._lock_token_matches(lock_dir, token)


def test_write_lock_metadata_removes_temp_file_on_replace_failure(
    tmp_path, monkeypatch
):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    token = "2" * 32
    lock_dir.mkdir(parents=True)

    def fail_replace(tmp_path, path):
        raise OSError("metadata replace failed")

    monkeypatch.setattr(currency.os, "replace", fail_replace)

    with pytest.raises(OSError, match="metadata replace failed"):
        currency._write_lock_metadata(lock_dir, token)

    assert list(lock_dir.glob(".metadata.*.tmp")) == []


def test_metadata_write_failure_does_not_delete_replacement_lock(
    tmp_path, monkeypatch
):
    replacement_token = "a" * 32

    def fail_after_replacement(path, token):
        lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
        shutil.rmtree(lock_dir)
        lock_dir.mkdir()
        write_lock_metadata(lock_dir, replacement_token)
        raise OSError("metadata failed")

    monkeypatch.setattr(
        currency,
        "_write_lock_metadata",
        fail_after_replacement,
    )

    with pytest.raises(OSError, match="metadata failed"):
        currency.acquire_refresh_lock(tmp_path, "isk")

    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    assert lock_dir.is_dir()
    assert read_lock_metadata(lock_dir)["token"] == replacement_token
    currency.RefreshLock(
        path=str(lock_dir),
        acquired=True,
        token=replacement_token,
    ).release()


def test_old_non_mapping_lock_metadata_can_be_recovered(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    metadata = lock_metadata_path(lock_dir, "b" * 32)
    metadata.write_text(json.dumps([]), encoding="utf-8")
    old_time = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    ).timestamp()
    os.utime(lock_dir, (old_time, old_time))

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is True
    recovered.release()


def test_malformed_lock_can_be_recovered_when_stale(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    metadata = tmp_path / "currency" / "locks" / "isk.lock" / "metadata.json"
    metadata.write_text(
        json.dumps({"created_at": "not-a-date"}),
        encoding="utf-8",
    )
    old_time = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    ).timestamp()
    os.utime(lock_dir, (old_time, old_time))

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is True
    recovered.release()


def test_naive_timestamp_lock_can_be_recovered_when_stale(tmp_path):
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    lock_metadata_path(lock_dir, "c" * 32).write_text(
        json.dumps({
            "created_at": dt.datetime.now().isoformat(),
            "token": "c" * 32,
        }),
        encoding="utf-8",
    )
    old_time = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    ).timestamp()
    os.utime(lock_dir, (old_time, old_time))

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is True
    recovered.release()


def test_stale_cleanup_does_not_delete_replacement_lock(
    tmp_path, monkeypatch
):
    old_lock = currency.acquire_refresh_lock(tmp_path, "isk")
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    stale_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    write_lock_metadata(lock_dir, old_lock.token, created_at=stale_time)
    replacement_token = "3" * 32
    original_remove = currency._remove_stale_lock_path

    def replace_then_remove(path, *args, **kwargs):
        # This simulates non-cooperating filesystem mutation at the race
        # boundary; cooperating converter processes are serialized by mutex.
        shutil.rmtree(lock_dir)
        lock_dir.mkdir()
        write_lock_metadata(lock_dir, replacement_token)
        original_remove(path, *args, **kwargs)

    monkeypatch.setattr(
        currency,
        "_remove_stale_lock_path",
        replace_then_remove,
    )

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert recovered.acquired is False
    assert lock_dir.is_dir()
    assert read_lock_metadata(lock_dir)["token"] == replacement_token
    currency.RefreshLock(
        path=str(lock_dir),
        acquired=True,
        token=replacement_token,
    ).release()


def test_acquire_uses_mutex_while_cleaning_stale_lock(
    tmp_path, monkeypatch
):
    old_lock = currency.acquire_refresh_lock(tmp_path, "isk")
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    stale_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    write_lock_metadata(lock_dir, old_lock.token, created_at=stale_time)
    events = []
    original_remove = currency._remove_stale_lock_path

    @contextlib.contextmanager
    def fake_mutex(path):
        events.append(("enter", os.fspath(path)))
        try:
            yield
        finally:
            events.append(("exit", os.fspath(path)))

    def record_remove(path, cleanup):
        events.append(("cleanup", os.fspath(path)))
        original_remove(path, cleanup)

    monkeypatch.setattr(currency, "_lock_path_mutex", fake_mutex)
    monkeypatch.setattr(currency, "_remove_stale_lock_path", record_remove)

    recovered = currency.acquire_refresh_lock(
        tmp_path,
        "isk",
        stale_after=dt.timedelta(minutes=5),
    )

    assert events[:3] == [
        ("enter", os.fspath(lock_dir)),
        ("cleanup", os.fspath(lock_dir)),
        ("exit", os.fspath(lock_dir)),
    ]
    assert recovered.acquired is True
    recovered.release()


def test_refresh_lock_release_uses_mutex_while_removing_metadata(
    tmp_path, monkeypatch
):
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    events = []
    inside_mutex = []
    original_remove = currency._remove_owned_lock_metadata

    @contextlib.contextmanager
    def fake_mutex(path):
        events.append(("enter", os.fspath(path)))
        inside_mutex.append(True)
        try:
            yield
        finally:
            inside_mutex.pop()
            events.append(("exit", os.fspath(path)))

    def record_remove(path, token):
        events.append(("remove", bool(inside_mutex)))
        return original_remove(path, token)

    monkeypatch.setattr(currency, "_lock_path_mutex", fake_mutex)
    monkeypatch.setattr(
        currency,
        "_remove_owned_lock_metadata",
        record_remove,
    )

    lock.release()

    assert events == [
        ("enter", lock.path),
        ("remove", True),
        ("exit", lock.path),
    ]
    assert not lock.acquired
    assert not (tmp_path / "currency" / "locks" / "isk.lock").exists()


def test_stale_cleanup_non_directory_plan_preserves_replacement_lock(
    tmp_path,
):
    lock_path = tmp_path / "currency" / "locks" / "isk.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("not a directory", encoding="utf-8")
    cleanup = currency._stale_lock_cleanup(
        lock_path,
        stale_after=dt.timedelta(minutes=5),
    )
    replacement_token = "4" * 32
    lock_path.unlink()
    lock_path.mkdir()
    write_lock_metadata(lock_path, replacement_token)

    currency._remove_stale_lock_path(lock_path, cleanup)

    assert lock_path.is_dir()
    assert read_lock_metadata(lock_path)["token"] == replacement_token
    currency.RefreshLock(
        path=str(lock_path),
        acquired=True,
        token=replacement_token,
    ).release()


def test_missing_lock_cleanup_plan_is_retryable(tmp_path):
    lock_path = tmp_path / "currency" / "locks" / "isk.lock"

    cleanup = currency._stale_lock_cleanup(
        lock_path,
        stale_after=dt.timedelta(minutes=5),
    )
    currency._remove_stale_lock_path(lock_path, cleanup)

    assert not lock_path.exists()


def test_lock_file_can_be_recovered(tmp_path):
    lock_path = tmp_path / "currency" / "locks" / "isk.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("not a directory", encoding="utf-8")

    recovered = currency.acquire_refresh_lock(tmp_path, "isk")

    assert recovered.acquired is True
    recovered.release()


def test_refresh_writes_cache_with_lock(tmp_path, monkeypatch):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    monkeypatch.setattr(currency, "fetch_rates", lambda base: fetched)

    result = currency.refresh_rates(tmp_path, "isk")

    assert result == fetched
    assert currency.read_rate_cache(tmp_path, "isk") == fetched


def test_refresh_returns_existing_cache_when_lock_unavailable(
    tmp_path, monkeypatch
):
    existing = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, existing)
    lock = currency.acquire_refresh_lock(tmp_path, "isk")

    result = currency.refresh_rates(tmp_path, "isk")

    assert result == existing
    lock.release()


def test_refresh_raises_when_lock_unavailable_without_cache(tmp_path):
    lock = currency.acquire_refresh_lock(tmp_path, "isk")

    with pytest.raises(RuntimeError, match="Unable to acquire refresh lock"):
        currency.refresh_rates(tmp_path, "isk")

    lock.release()


def test_refresh_rates_with_existing_lock_writes_cache_and_releases(
    tmp_path, monkeypatch
):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    monkeypatch.setattr(currency, "fetch_rates", lambda base: fetched)

    result = currency.refresh_rates_with_existing_lock(
        tmp_path,
        "isk",
        lock.path,
        token=lock.token,
    )

    assert result == fetched
    assert currency.read_rate_cache(tmp_path, "isk") == fetched
    assert not (tmp_path / "currency" / "locks" / "isk.lock").exists()


def test_refresh_rates_with_existing_lock_rejects_missing_lock_token(
    tmp_path, monkeypatch
):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    expected_path = tmp_path / "currency" / "locks" / "isk.lock"
    calls = []
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: calls.append(base) or fetched,
    )

    with pytest.raises(ValueError, match="refresh lock"):
        currency.refresh_rates_with_existing_lock(
            tmp_path,
            "isk",
            expected_path,
        )

    assert calls == []
    assert currency.read_rate_cache(tmp_path, "isk") is None


def test_refresh_rates_with_existing_lock_rejects_existing_lock_missing_token(
    tmp_path, monkeypatch
):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    calls = []
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: calls.append(base) or fetched,
    )

    with pytest.raises(ValueError, match="refresh lock"):
        currency.refresh_rates_with_existing_lock(tmp_path, "isk", lock.path)

    assert calls == []
    lock.release()


def test_refresh_rates_with_existing_lock_rejects_unreadable_metadata(
    tmp_path, monkeypatch
):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_dir.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: calls.append(base) or fetched,
    )

    with pytest.raises(ValueError, match="refresh lock"):
        currency.refresh_rates_with_existing_lock(
            tmp_path,
            "isk",
            lock_dir,
            token="missing-metadata-token",
        )

    assert calls == []
    assert lock_dir.is_dir()


def test_refresh_rates_with_existing_lock_rejects_wrong_token(
    tmp_path, monkeypatch
):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    calls = []
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: calls.append(base) or fetched,
    )

    with pytest.raises(ValueError, match="refresh lock"):
        currency.refresh_rates_with_existing_lock(
            tmp_path,
            "isk",
            lock.path,
            token="wrong-token",
        )

    assert calls == []
    assert (tmp_path / "currency" / "locks" / "isk.lock").is_dir()
    lock.release()


def test_refresh_lock_release_preserves_newer_owner(tmp_path):
    old_lock = currency.acquire_refresh_lock(tmp_path, "isk")
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    lock_metadata_path(lock_dir, old_lock.token).unlink()
    new_token = "d" * 32
    write_lock_metadata(lock_dir, new_token)

    old_lock.release()

    assert not old_lock.acquired
    assert lock_dir.is_dir()
    currency.RefreshLock(
        path=old_lock.path,
        acquired=True,
        token=new_token,
    ).release()


def test_release_does_not_delete_replacement_lock_during_cleanup(
    tmp_path, monkeypatch
):
    old_lock = currency.acquire_refresh_lock(tmp_path, "isk")
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    replacement_token = "e" * 32
    original_rmdir = currency.os.rmdir

    def replace_lock():
        if lock_dir.exists():
            for child in lock_dir.iterdir():
                child.unlink()
            original_rmdir(lock_dir)
        lock_dir.mkdir()
        write_lock_metadata(lock_dir, replacement_token)

    def rmdir_after_replacement(path, *args, **kwargs):
        if (
            os.fspath(path) == os.fspath(lock_dir)
            and kwargs.get("dir_fd") is None
        ):
            replace_lock()
            raise OSError("lock replaced")
        return original_rmdir(path, *args, **kwargs)

    monkeypatch.setattr(currency.os, "rmdir", rmdir_after_replacement)

    old_lock.release()

    assert not old_lock.acquired
    assert lock_dir.is_dir()
    assert read_lock_metadata(lock_dir)["token"] == replacement_token
    currency.RefreshLock(
        path=str(lock_dir),
        acquired=True,
        token=replacement_token,
    ).release()


def test_refresh_rates_with_existing_lock_rejects_arbitrary_path(tmp_path):
    outside = tmp_path / "outside.lock"
    outside.mkdir()

    with pytest.raises(ValueError, match="invalid refresh lock path"):
        currency.refresh_rates_with_existing_lock(tmp_path, "isk", outside)

    assert outside.exists()


def test_start_background_refresh_does_not_launch_when_locked(
    tmp_path, monkeypatch
):
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    launched = []

    monkeypatch.setattr(
        currency.subprocess,
        "Popen",
        lambda *args, **kwargs: launched.append(args),
    )

    assert currency.start_background_refresh(tmp_path, "isk") is False
    assert launched == []

    lock.release()


def test_start_background_refresh_transfers_lock_to_worker(
    tmp_path, monkeypatch
):
    import os

    launched = []

    def fake_popen(command, **kwargs):
        launched.append((command, kwargs))

    monkeypatch.setattr(currency.subprocess, "Popen", fake_popen)

    assert currency.start_background_refresh(tmp_path, "isk") is True

    command, kwargs = launched[0]
    assert command[3] == "update-locked"
    assert command[4] == "isk"
    assert os.path.isdir(command[5])
    token = kwargs["env"][currency.LOCK_TOKEN_ENV]
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    data = read_lock_metadata(lock_dir)
    assert data["token"] == token
    currency.RefreshLock(
        path=command[5],
        acquired=True,
        token=token,
    ).release()


def test_start_background_refresh_releases_lock_when_launch_fails(
    tmp_path, monkeypatch
):
    def fake_popen(command, **kwargs):
        raise OSError("cannot launch")

    monkeypatch.setattr(currency.subprocess, "Popen", fake_popen)

    assert currency.start_background_refresh(tmp_path, "isk") is False
    assert not (tmp_path / "currency" / "locks" / "isk.lock").exists()


def test_start_background_refresh_uses_worker_process_options(
    tmp_path, monkeypatch
):
    launched = []

    def fake_popen(command, **kwargs):
        launched.append((command, kwargs))

    monkeypatch.setattr(currency.subprocess, "Popen", fake_popen)

    assert currency.start_background_refresh(tmp_path, "isk") is True

    command, kwargs = launched[0]
    assert command[:5] == [
        currency.sys.executable,
        "-m",
        "converter.currency",
        "update-locked",
        "isk",
    ]
    assert kwargs["stdin"] == currency.subprocess.DEVNULL
    assert kwargs["stdout"] == currency.subprocess.DEVNULL
    assert kwargs["stderr"] == currency.subprocess.DEVNULL
    assert kwargs["close_fds"] is True
    assert kwargs["env"]["alfred_workflow_cache"] == str(tmp_path)
    token = kwargs["env"][currency.LOCK_TOKEN_ENV]
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    data = read_lock_metadata(lock_dir)
    assert data["token"] == token
    currency.RefreshLock(
        path=command[5],
        acquired=True,
        token=token,
    ).release()


def test_start_background_refresh_without_base_dir_passes_token_env(
    tmp_path, monkeypatch
):
    launched = []

    def fake_popen(command, **kwargs):
        launched.append((command, kwargs))

    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))
    monkeypatch.setattr(currency.subprocess, "Popen", fake_popen)

    assert currency.start_background_refresh(None, "isk") is True

    command, kwargs = launched[0]
    token = kwargs["env"][currency.LOCK_TOKEN_ENV]
    lock_dir = tmp_path / "currency" / "locks" / "isk.lock"
    data = read_lock_metadata(lock_dir)
    assert command[4] == "isk"
    assert data["token"] == token
    currency.RefreshLock(
        path=command[5],
        acquired=True,
        token=token,
    ).release()


def test_main_update_invokes_refresh(monkeypatch):
    calls = []

    monkeypatch.setattr(
        currency,
        "refresh_rates",
        lambda base_dir, base: calls.append((base_dir, base)),
    )

    assert currency.main(["update", "isk"]) == 0
    assert calls == [(None, "isk")]


def test_main_update_locked_invokes_refresh_with_existing_lock(monkeypatch):
    calls = []

    monkeypatch.setattr(
        currency,
        "refresh_rates_with_existing_lock",
        lambda base_dir, base, lock_path, token=None: calls.append(
            (base_dir, base, lock_path, token)
        ),
    )
    monkeypatch.setenv(
        currency.LOCK_TOKEN_ENV,
        "worker-token",
    )

    assert currency.main(["update-locked", "isk", "/tmp/isk.lock"]) == 0
    assert calls == [(None, "isk", "/tmp/isk.lock", "worker-token")]


def test_main_rejects_invalid_usage():
    with pytest.raises(
        SystemExit,
        match="Usage: python -m converter.currency",
    ):
        currency.main(["invalid"])


def test_main_honors_explicit_empty_argv(monkeypatch):
    calls = []

    monkeypatch.setattr(currency.sys, "argv", ["currency.py", "update", "isk"])
    monkeypatch.setattr(
        currency,
        "refresh_rates",
        lambda base_dir, base: calls.append((base_dir, base)),
    )

    with pytest.raises(
        SystemExit,
        match="Usage: python -m converter.currency",
    ):
        currency.main([])

    assert calls == []
