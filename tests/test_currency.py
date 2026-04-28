import contextlib
import datetime as dt
import decimal
import json
import os
import shutil
import struct
import urllib.error
import zlib
from pathlib import Path

import pytest

from converter import currency


REPO_ROOT = Path(__file__).resolve().parents[1]


def _png_size_and_alpha_bbox(path):
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")

    cursor = 8
    idat_chunks = []
    palette_alpha = b""
    while cursor < len(data):
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        chunk_type = data[cursor + 4:cursor + 8]
        chunk_data = data[cursor + 8:cursor + 8 + length]
        cursor += length + 12

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = (
                struct.unpack(">IIBBBBB", chunk_data)
            )
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"tRNS":
            palette_alpha = chunk_data
        elif chunk_type == b"IEND":
            break

    assert bit_depth == 8
    assert color_type in {3, 4, 6}
    assert interlace == 0

    bytes_per_pixel = {3: 1, 4: 2, 6: 4}[color_type]
    row_length = width * bytes_per_pixel
    raw = zlib.decompress(b"".join(idat_chunks))
    previous = bytearray(row_length)
    bbox = None
    offset = 0

    for y in range(height):
        filter_type = raw[offset]
        row = bytearray(raw[offset + 1:offset + 1 + row_length])
        offset += row_length + 1

        for x in range(row_length):
            left = row[x - bytes_per_pixel] if x >= bytes_per_pixel else 0
            up = previous[x]
            up_left = (
                previous[x - bytes_per_pixel]
                if x >= bytes_per_pixel
                else 0
            )

            if filter_type == 1:
                row[x] = (row[x] + left) & 0xFF
            elif filter_type == 2:
                row[x] = (row[x] + up) & 0xFF
            elif filter_type == 3:
                row[x] = (row[x] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[x] = (row[x] + _paeth(left, up, up_left)) & 0xFF
            else:
                assert filter_type == 0

        for x in range(width):
            if color_type == 3:
                palette_index = row[x]
                alpha = (
                    palette_alpha[palette_index]
                    if palette_index < len(palette_alpha)
                    else 255
                )
            else:
                alpha_offset = 1 if color_type == 4 else 3
                alpha = row[(x * bytes_per_pixel) + alpha_offset]

            if alpha:
                if bbox is None:
                    bbox = [x, y, x + 1, y + 1]
                else:
                    bbox[0] = min(bbox[0], x)
                    bbox[1] = min(bbox[1], y)
                    bbox[2] = max(bbox[2], x + 1)
                    bbox[3] = max(bbox[3], y + 1)

        previous = row

    return (width, height), None if bbox is None else tuple(bbox)


def _paeth(left, up, up_left):
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)

    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


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


def test_parse_default_currency_query_uses_default_targets(monkeypatch):
    monkeypatch.delenv(currency.DEFAULT_TARGETS_ENV, raising=False)

    assert currency.parse_default_query("5 usd") == currency.DefaultQuery(
        amount=decimal.Decimal("5"),
        source="usd",
        targets=("eur", "gbp", "jpy", "cny", "cad", "aud"),
    )
    assert currency.parse_default_query("5 eur") == currency.DefaultQuery(
        amount=decimal.Decimal("5"),
        source="eur",
        targets=("usd", "gbp", "jpy", "cny", "cad", "aud"),
    )


def test_parse_default_currency_query_uses_configured_targets(monkeypatch):
    monkeypatch.setenv(currency.DEFAULT_TARGETS_ENV, "EUR JPY, cny")

    assert currency.parse_default_query("5 usd") == currency.DefaultQuery(
        amount=decimal.Decimal("5"),
        source="usd",
        targets=("eur", "jpy", "cny"),
    )


def test_parse_default_currency_query_excludes_source_and_duplicates(
    monkeypatch,
):
    monkeypatch.setenv(currency.DEFAULT_TARGETS_ENV, "usd eur USD gbp")

    assert currency.parse_default_query("5 usd") == currency.DefaultQuery(
        amount=decimal.Decimal("5"),
        source="usd",
        targets=("eur", "gbp"),
    )


def test_parse_default_currency_query_rejects_invalid_source():
    assert currency.parse_default_query("5 foo") is None


def test_parse_default_currency_query_rejects_grouped_amounts():
    assert currency.parse_default_query("1,000 usd") is None


def test_currency_symbols_use_common_display_values():
    assert currency.currency_symbol("usd") == "$"
    assert currency.currency_symbol("eur") == "€"
    assert currency.currency_symbol("cny") == "CN¥"
    assert currency.currency_symbol("isk") == "kr"


def test_currency_icon_path_uses_flag_when_currency_has_logical_region():
    assert (
        currency.currency_icon_path("usd")
        == "icons/currencies/flags/usd.png"
    )
    assert (
        currency.currency_icon_path("eur")
        == "icons/currencies/flags/eur.png"
    )
    assert (
        currency.currency_icon_path("cad")
        == "icons/currencies/flags/cad.png"
    )


def test_currency_icon_path_keeps_neutral_badge_for_regional_currency():
    assert currency.currency_icon_path("xof") == "icons/currencies/xof.png"


def test_currency_icon_assets_exist_for_all_currency_codes():
    missing = [
        code for code in sorted(currency.CURRENCY_CODES)
        if not (REPO_ROOT / currency.currency_icon_path(code)).exists()
    ]

    assert missing == []


def test_currency_icons_use_unit_icon_canvas_style():
    unit_size, _ = _png_size_and_alpha_bbox(REPO_ROOT / "icons/ruler9.png")
    assert unit_size == (512, 512)

    for icon_path in (
        "icons/currencies/flags/usd.png",
        "icons/currencies/flags/eur.png",
        "icons/currencies/xof.png",
    ):
        icon_size, bbox = _png_size_and_alpha_bbox(REPO_ROOT / icon_path)

        assert icon_size == unit_size
        assert bbox is not None
        assert bbox[0] > 0
        assert bbox[1] > 0
        assert bbox[2] < icon_size[0]
        assert bbox[3] < icon_size[1]


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


def test_read_rate_cache_normalizes_uppercase_rate_keys(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()
    (rate_dir / "isk.json").write_text(
        json.dumps(
            {
                "base": "isk",
                "date": "2026-04-24",
                "fetched_at": dt.date.today().isoformat(),
                "rates": {"EUR": "0.0069542179"},
            }
        ),
        encoding="utf-8",
    )

    loaded = currency.read_rate_cache(tmp_path, "isk")
    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert loaded.rates == {"eur": decimal.Decimal("0.0069542179")}
    assert response.items[0].title == (
        "2000 ISK (kr) = 13.908436 EUR (€)"
    )
    assert response.items[0].valid is True
    assert response.items[0].icon == "icons/currencies/flags/eur.png"


def test_read_rate_cache_rejects_invalid_rate_key(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()
    (rate_dir / "isk.json").write_text(
        json.dumps(
            {
                "base": "isk",
                "date": "2026-04-24",
                "fetched_at": dt.date.today().isoformat(),
                "rates": {"not-currency": "1"},
            }
        ),
        encoding="utf-8",
    )

    assert currency.read_rate_cache(tmp_path, "isk") is None


def test_read_rate_cache_rejects_duplicate_normalized_rate_keys(tmp_path):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()
    (rate_dir / "isk.json").write_text(
        json.dumps(
            {
                "base": "isk",
                "date": "2026-04-24",
                "fetched_at": dt.date.today().isoformat(),
                "rates": {
                    "EUR": "0.0069542179",
                    "eur": "0.0069542180",
                },
            }
        ),
        encoding="utf-8",
    )

    assert currency.read_rate_cache(tmp_path, "isk") is None


@pytest.mark.parametrize("rate", ["0", "-0.1"])
def test_read_rate_cache_rejects_non_positive_rates(tmp_path, rate):
    rate_dir = tmp_path / "currency"
    rate_dir.mkdir()
    (rate_dir / "isk.json").write_text(
        json.dumps(
            {
                "base": "isk",
                "date": "2026-04-24",
                "fetched_at": dt.date.today().isoformat(),
                "rates": {"eur": rate},
            }
        ),
        encoding="utf-8",
    )

    assert currency.read_rate_cache(tmp_path, "isk") is None


def test_write_rate_cache_normalizes_rate_keys(tmp_path):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"EUR": decimal.Decimal("0.0069542179")},
    )

    currency.write_rate_cache(tmp_path, cache)

    data = json.loads(
        (tmp_path / "currency" / "isk.json").read_text(encoding="utf-8")
    )
    assert data["rates"] == {"eur": "0.0069542179"}


def test_provider_payload_ignores_unsupported_rate_keys():
    cache = currency._rate_cache_from_payload(
        "eur",
        {
            "date": "2026-04-25",
            "eur": {
                "usd": "1.136986",
                "btc": "0.000011",
                "1inch": "3.4",
            },
        },
    )

    assert cache.rates == {"usd": decimal.Decimal("1.136986")}


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


def test_convert_with_fresh_cache_returns_valid_item(tmp_path):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].title == (
        "2000 ISK (kr) = 13.908436 EUR (€)"
    )
    assert response.items[0].arg == "13.908436"
    assert response.items[0].icon == "icons/currencies/flags/eur.png"
    assert response.items[0].subtitle == (
        "Icelandic Krona to Euro - Rates from 2026-04-24"
    )


def test_convert_default_query_returns_default_target_items(tmp_path):
    cache = currency.RateCache(
        base="usd",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={
            "eur": decimal.Decimal("0.9"),
            "gbp": decimal.Decimal("0.8"),
            "jpy": decimal.Decimal("150"),
            "cny": decimal.Decimal("7.2"),
            "cad": decimal.Decimal("1.3"),
            "aud": decimal.Decimal("1.5"),
        },
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, "5 usd")

    assert [item.title for item in response.items] == [
        "5 USD ($) = 4.5 EUR (€)",
        "5 USD ($) = 4 GBP (£)",
        "5 USD ($) = 750 JPY (¥)",
        "5 USD ($) = 36 CNY (CN¥)",
        "5 USD ($) = 6.5 CAD (CA$)",
        "5 USD ($) = 7.5 AUD (A$)",
    ]
    assert [item.icon for item in response.items] == [
        "icons/currencies/flags/eur.png",
        "icons/currencies/flags/gbp.png",
        "icons/currencies/flags/jpy.png",
        "icons/currencies/flags/cny.png",
        "icons/currencies/flags/cad.png",
        "icons/currencies/flags/aud.png",
    ]
    assert response.items[0].subtitle == (
        "US Dollar to Euro - Rates from 2026-04-24"
    )


def test_convert_default_query_includes_usd_for_eur_source(tmp_path):
    cache = currency.RateCache(
        base="eur",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={
            "usd": decimal.Decimal("1.1"),
            "gbp": decimal.Decimal("0.8"),
            "jpy": decimal.Decimal("150"),
            "cny": decimal.Decimal("7.2"),
            "cad": decimal.Decimal("1.3"),
            "aud": decimal.Decimal("1.5"),
        },
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, "5 eur")

    assert [item.title for item in response.items] == [
        "5 EUR (€) = 5.5 USD ($)",
        "5 EUR (€) = 4 GBP (£)",
        "5 EUR (€) = 750 JPY (¥)",
        "5 EUR (€) = 36 CNY (CN¥)",
        "5 EUR (€) = 6.5 CAD (CA$)",
        "5 EUR (€) = 7.5 AUD (A$)",
    ]
    assert response.items[0].icon == "icons/currencies/flags/usd.png"
    assert response.items[0].subtitle == (
        "Euro to US Dollar - Rates from 2026-04-24"
    )


def test_convert_default_query_with_stale_cache_marks_each_result(
    tmp_path,
    monkeypatch,
):
    cache = currency.RateCache(
        base="usd",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 24),
        rates={
            "eur": decimal.Decimal("0.9"),
            "gbp": decimal.Decimal("0.8"),
        },
    )
    currency.write_rate_cache(tmp_path, cache)
    monkeypatch.setenv(currency.DEFAULT_TARGETS_ENV, "eur,gbp")
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: currency.BACKGROUND_REFRESH_STARTED,
    )

    response = currency.convert_query(
        tmp_path,
        "5 usd",
        today=dt.date(2026, 4, 25),
    )

    assert [item.title for item in response.items] == [
        "5 USD ($) = 4.5 EUR (€)",
        "5 USD ($) = 4 GBP (£)",
    ]
    assert all("stale, refreshing" in item.subtitle for item in response.items)


def test_convert_with_stale_cache_returns_result_and_refreshes(
    tmp_path,
    monkeypatch,
):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 24),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, cache)
    launched = []
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: launched.append((base_dir, base))
        or currency.BACKGROUND_REFRESH_STARTED,
    )

    response = currency.convert_query(
        tmp_path,
        "2000 isk eur",
        today=dt.date(2026, 4, 25),
    )

    assert response.items[0].arg == "13.908436"
    assert "stale" in response.items[0].subtitle.lower()
    assert launched == [(tmp_path, "isk")]


def test_convert_with_stale_cache_does_not_claim_refresh_when_launch_fails(
    tmp_path,
    monkeypatch,
):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 24),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, cache)
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: currency.BACKGROUND_REFRESH_FAILED,
    )

    response = currency.convert_query(
        tmp_path,
        "2000 isk eur",
        today=dt.date(2026, 4, 25),
    )

    assert response.items[0].valid is True
    assert response.items[0].arg == "13.908436"
    assert "stale" in response.items[0].subtitle.lower()
    assert "refreshing" not in response.items[0].subtitle.lower()


def test_convert_with_stale_cache_treats_existing_lock_as_refreshing(
    tmp_path,
    monkeypatch,
):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 24),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, cache)
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    monkeypatch.setattr(
        currency.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Popen called")
        ),
    )

    response = currency.convert_query(
        tmp_path,
        "2000 isk eur",
        today=dt.date(2026, 4, 25),
    )

    assert response.items[0].valid is True
    assert response.items[0].arg == "13.908436"
    assert "refreshing" in response.items[0].subtitle.lower()
    assert "unavailable" not in response.items[0].subtitle.lower()
    lock.release()


def test_convert_without_cache_returns_updating_item(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: launched.append((base_dir, base))
        or currency.BACKGROUND_REFRESH_STARTED,
    )

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency rates updating"
    assert launched == [(tmp_path, "isk")]


def test_convert_without_cache_treats_existing_lock_as_updating(
    tmp_path,
    monkeypatch,
):
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    monkeypatch.setattr(
        currency.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Popen called")
        ),
    )

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency rates updating"
    assert response.rerun == 1
    lock.release()


def test_convert_without_cache_reports_background_launch_failure(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: currency.BACKGROUND_REFRESH_FAILED,
    )

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].valid is False
    assert response.items[0].title != "Currency rates updating"
    assert response.items[0].title == "Currency rates unavailable"
    assert "background update" in response.items[0].subtitle
    assert response.rerun is None


def test_convert_without_cache_reports_popen_launch_failure(
    tmp_path,
    monkeypatch,
):
    def fail_popen(command, **kwargs):
        raise OSError("cannot launch")

    monkeypatch.setattr(currency.subprocess, "Popen", fail_popen)

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency rates unavailable"
    assert response.rerun is None


def test_convert_without_cache_does_not_refresh_synchronously(
    tmp_path,
    monkeypatch,
):
    launched = []
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: launched.append((base_dir, base))
        or currency.BACKGROUND_REFRESH_STARTED,
    )
    monkeypatch.setattr(
        currency,
        "refresh_rates",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("refresh_rates called")
        ),
    )
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fetch_rates called")
        ),
    )

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].title == "Currency rates updating"
    assert launched == [(tmp_path, "isk")]


def test_convert_with_stale_cache_does_not_refresh_synchronously(
    tmp_path,
    monkeypatch,
):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 24),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, cache)
    launched = []
    monkeypatch.setattr(
        currency,
        "start_background_refresh_status",
        lambda base_dir, base: launched.append((base_dir, base))
        or currency.BACKGROUND_REFRESH_STARTED,
    )
    monkeypatch.setattr(
        currency,
        "refresh_rates",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("refresh_rates called")
        ),
    )
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fetch_rates called")
        ),
    )

    response = currency.convert_query(
        tmp_path,
        "2000 isk eur",
        today=dt.date(2026, 4, 25),
    )

    assert response.items[0].arg == "13.908436"
    assert launched == [(tmp_path, "isk")]


def test_convert_missing_target_rate_returns_unavailable_item(tmp_path):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={"usd": decimal.Decimal("0.0075")},
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency EUR unavailable"


def test_convert_unparsed_query_returns_none(tmp_path):
    assert currency.convert_query(tmp_path, "1 m in cm") is None


def test_convert_large_decimal_amount_does_not_crash(tmp_path):
    amount = "9" * 40
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={"eur": decimal.Decimal("1")},
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, f"{amount} isk eur")

    assert response.items[0].valid is True
    assert response.items[0].arg == amount
    assert response.items[0].title == (
        f"{amount} ISK (kr) = {amount} EUR (€)"
    )


def test_convert_tiny_nonzero_result_does_not_format_as_zero(tmp_path):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={"eur": decimal.Decimal("0.0000000002")},
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, "2000 isk eur")

    assert response.items[0].valid is True
    assert response.items[0].arg == "0.0000004"
    assert "0.0000004 EUR" in response.items[0].title


def test_convert_tiny_negative_result_does_not_format_as_negative_zero(
    tmp_path,
):
    cache = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date.today(),
        rates={"eur": decimal.Decimal("0.0000000002")},
    )
    currency.write_rate_cache(tmp_path, cache)

    response = currency.convert_query(tmp_path, "-1 isk eur")

    assert response.items[0].valid is True
    assert response.items[0].arg == "-0.0000000002"
    assert "-0 EUR" not in response.items[0].title


def test_manual_update_success(tmp_path, monkeypatch):
    fetched = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={
            "eur": decimal.Decimal("0.0069542179"),
            "usd": decimal.Decimal("0.0075"),
        },
    )
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: fetched,
    )

    response = currency.update_command(tmp_path, "currency-update isk")

    assert response.items[0].title == "Updated ISK currency rates"
    assert "2 currencies" in response.items[0].subtitle


def test_manual_update_failure(tmp_path, monkeypatch):
    def fail(base):
        raise RuntimeError("network down")

    monkeypatch.setattr(currency, "fetch_rates", fail)

    response = currency.update_command(tmp_path, "currency-update isk")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency update failed"
    assert "network down" in response.items[0].subtitle


def test_manual_update_reports_already_running_instead_of_cached_success(
    tmp_path,
    monkeypatch,
):
    existing = currency.RateCache(
        base="isk",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 24),
        rates={"eur": decimal.Decimal("0.0069542179")},
    )
    currency.write_rate_cache(tmp_path, existing)
    lock = currency.acquire_refresh_lock(tmp_path, "isk")
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: (_ for _ in ()).throw(
            AssertionError("fetch_rates called")
        ),
    )

    response = currency.update_command(tmp_path, "currency-update isk")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency update already running"
    assert "Updated" not in response.items[0].title
    assert "already refreshing" in response.items[0].subtitle
    lock.release()


def test_manual_update_defaults_to_eur(tmp_path, monkeypatch):
    calls = []
    fetched = currency.RateCache(
        base="eur",
        date=dt.date(2026, 4, 24),
        fetched_at=dt.date(2026, 4, 25),
        rates={"usd": decimal.Decimal("1.14052")},
    )
    monkeypatch.setattr(
        currency,
        "fetch_rates",
        lambda base: calls.append(base) or fetched,
    )

    response = currency.update_command(tmp_path, "currency-update")

    assert response.items[0].title == "Updated EUR currency rates"
    assert calls == ["eur"]


def test_manual_update_invalid_base_returns_failure_item(tmp_path):
    response = currency.update_command(tmp_path, "currency-update zzz")

    assert response.items[0].valid is False
    assert response.items[0].title == "Currency update failed"
    assert "invalid currency base" in response.items[0].subtitle


def test_manual_update_invalid_command_returns_failure_without_refresh(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fail_manual_refresh(base_dir, base):
        calls.append((base_dir, base))
        raise AssertionError("manual refresh called")

    monkeypatch.setattr(currency, "manual_refresh_rates", fail_manual_refresh)

    response = currency.update_command(tmp_path, "not-update")

    assert response.items[0].valid is False
    assert response.items[0].title == "Invalid currency update command"
    assert calls == []


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
        calls.append((request, timeout))
        return FakeResponse({
            "date": "2026-04-24",
            "isk": {"eur": 0.0069542179},
        })

    monkeypatch.setattr(currency.urllib.request, "urlopen", fake_urlopen)

    cache = currency.fetch_rates("isk")

    request, timeout = calls[0]
    assert request.full_url == (
        "https://cdn.jsdelivr.net/npm/"
        "@fawazahmed0/currency-api@latest/v1/currencies/isk.json"
    )
    assert timeout == 10
    assert request.get_header("User-agent") == "alfred-converter/1"
    assert cache.rates["eur"] == decimal.Decimal("0.0069542179")


def test_fetch_rates_normalizes_provider_rate_keys(monkeypatch):
    monkeypatch.setattr(
        currency,
        "_load_json_url",
        lambda url: {
            "date": "2026-04-24",
            "isk": {"EUR": 0.0069542179},
        },
    )

    cache = currency.fetch_rates("isk")

    assert cache.rates == {"eur": decimal.Decimal("0.0069542179")}


def test_fetch_rates_rejects_duplicate_normalized_provider_rate_keys(
    monkeypatch,
):
    monkeypatch.setattr(
        currency,
        "_load_json_url",
        lambda url: {
            "date": "2026-04-24",
            "isk": {"EUR": 0.0069542179, "eur": 0.0069542180},
        },
    )

    with pytest.raises(RuntimeError, match="Unable to fetch rates for isk"):
        currency.fetch_rates("isk")


def test_fetch_rates_rejects_invalid_provider_rate_key(monkeypatch):
    monkeypatch.setattr(
        currency,
        "_load_json_url",
        lambda url: {
            "date": "2026-04-24",
            "isk": {"not-currency": 1},
        },
    )

    with pytest.raises(RuntimeError, match="Unable to fetch rates for isk"):
        currency.fetch_rates("isk")


@pytest.mark.parametrize("rate", ["0", "-0.1"])
def test_fetch_rates_rejects_non_positive_provider_rates(
    rate,
    monkeypatch,
):
    monkeypatch.setattr(
        currency,
        "_load_json_url",
        lambda url: {
            "date": "2026-04-24",
            "isk": {"eur": rate},
        },
    )

    with pytest.raises(RuntimeError, match="Unable to fetch rates for isk"):
        currency.fetch_rates("isk")


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
