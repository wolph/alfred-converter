from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import typing
import urllib.request
import uuid
from dataclasses import dataclass

from . import output

CURRENCY_CODES = frozenset("""
    aed afn all amd ang aoa ars aud awg azn bam bbd bdt bgn bhd bif bmd bnd
    bob bov brl bsd btn bwp byn bzd cad cdf che chf chw clf clp cny cop cou
    crc cuc cup cve czk djf dkk dop dzd egp ern etb eur fjd fkp gbp gel ghs
    gip gmd gnf gtq gyd hkd hnl htg huf idr ils inr iqd irr isk jmd jod jpy
    kes kgs khr kmf kpw krw kwd kyd kzt lak lbp lkr lrd lsl lyd mad mdl mga
    mkd mmk mnt mop mru mur mvr mwk mxn mxv myr mzn nad ngn nio nok npr nzd
    omr pab pen pgk php pkr pln pyg qar ron rsd rub rwf sar sbd scr sdg sek
    sgd shp sle sll sos srd ssp stn svc syp szl thb tjs tmt tnd top try ttd
    twd tzs uah ugx usd usn uyi uyu uzs ved ves vnd vuv wst xaf xag xau xba
    xbb xbc xbd xcd xdr xof xpd xpf xpt xsu xts xua xxx yer zar zmw zwg
""".split())

CURRENCY_QUERY_RE = re.compile(
    r"^\s*(?P<amount>[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))\s+"
    r"(?P<source>[a-zA-Z]{3})"
    r"(?:\s+(?:to|in|as))?\s+"
    r"(?P<target>[a-zA-Z]{3})\s*$"
)

DECIMAL_COMMA_RE = re.compile(r"^[+-]?(?:\d+,\d{1,2}|,\d+)$")
UPDATE_RE = re.compile(r"^\s*currency-update(?:\s+(?P<base>[a-zA-Z]{3}))?\s*$")

PRIMARY_URL = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/"
    "v1/currencies/{currency}.json"
)
FALLBACK_URL = (
    "https://latest.currency-api.pages.dev/v1/currencies/{currency}.json"
)
DEFAULT_LOCK_STALE_AFTER = dt.timedelta(minutes=10)
LOCK_TOKEN_ENV = "ALFRED_CONVERTER_CURRENCY_LOCK_TOKEN"
LOCK_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
BACKGROUND_REFRESH_STARTED = "started"
BACKGROUND_REFRESH_ALREADY_RUNNING = "already_running"
BACKGROUND_REFRESH_FAILED = "failed"


@dataclass(frozen=True)
class CurrencyQuery:
    amount: decimal.Decimal
    source: str
    target: str


@dataclass(frozen=True)
class RateCache:
    base: str
    date: dt.date
    fetched_at: dt.date
    rates: typing.Dict[str, decimal.Decimal]

    def is_fresh(self, today=None):
        today = today or dt.date.today()
        return self.fetched_at >= today


@dataclass
class RefreshLock:
    path: str
    acquired: bool
    token: typing.Optional[str] = None

    def release(self):
        if self.acquired:
            with _lock_path_mutex(self.path):
                removed_metadata = _remove_owned_lock_metadata(
                    self.path,
                    self.token,
                )
                if removed_metadata:
                    try:
                        os.rmdir(self.path)
                    except OSError:
                        pass
            self.acquired = False


@dataclass(frozen=True)
class _StaleLockCleanup:
    is_directory: bool
    metadata_filenames: typing.Tuple[str, ...] = ()
    st_dev: typing.Optional[int] = None
    st_ino: typing.Optional[int] = None


@contextlib.contextmanager
def _lock_path_mutex(path):
    # Static lock-path cleanup uses path-based rmdir, so cooperating
    # converter processes serialize the inspect/remove window.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(f"{path}.mutex", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def parse_query(query):
    match = CURRENCY_QUERY_RE.match(query)
    if not match:
        return None

    source = match.group("source").lower()
    target = match.group("target").lower()
    if source not in CURRENCY_CODES or target not in CURRENCY_CODES:
        return None

    amount_text = match.group("amount")
    if "," in amount_text and not DECIMAL_COMMA_RE.match(amount_text):
        return None

    amount = decimal.Decimal(amount_text.replace(",", "."))
    return CurrencyQuery(amount=amount, source=source, target=target)


def _format_decimal(value):
    integer_digits = max(value.adjusted() + 1, 1)
    coefficient_digits = len(value.as_tuple().digits)
    precision = max(integer_digits + 6, coefficient_digits, 28)
    with decimal.localcontext() as context:
        context.prec = precision
        quantized = value.quantize(decimal.Decimal("0.000001"))
    if quantized.is_zero() and not value.is_zero():
        formatted = format(value, "f").rstrip("0").rstrip(".")
        return "0" if formatted in {"", "-0"} else formatted
    if quantized.is_zero():
        return "0"
    return str(quantized).rstrip("0").rstrip(".")


def _normalize_rates(rates, key_error_message, value_error_message):
    if not isinstance(rates, dict):
        raise ValueError("rates must be a mapping")

    parsed_rates = {}
    for key, value in rates.items():
        if not isinstance(key, str):
            raise ValueError(key_error_message)
        normalized_key = key.lower()
        if normalized_key not in CURRENCY_CODES:
            raise ValueError(key_error_message)
        if normalized_key in parsed_rates:
            raise ValueError(key_error_message)
        rate = decimal.Decimal(str(value))
        if not rate.is_finite() or rate <= 0:
            raise ValueError(value_error_message)
        parsed_rates[normalized_key] = rate
    return parsed_rates


def _conversion_response(query, cache, stale=False, refresh_launched=False):
    rate = cache.rates.get(query.target)
    if rate is None:
        return output.Response(
            items=[
                output.Item(
                    title=f"Currency {query.target.upper()} unavailable",
                    subtitle=(
                        f"No {query.target.upper()} rate in "
                        f"{query.source.upper()} cache"
                    ),
                    valid=False,
                    icon="icons/dollars17.png",
                )
            ],
            skipknowledge=True,
        )

    multiplication_precision = max(
        len(query.amount.as_tuple().digits) + len(rate.as_tuple().digits) + 6,
        query.amount.adjusted() + rate.adjusted() + 8,
        28,
    )
    with decimal.localcontext() as context:
        context.prec = multiplication_precision
        converted = _format_decimal(query.amount * rate)
    subtitle = f"Rates from {cache.date.isoformat()}"
    if stale:
        if refresh_launched:
            subtitle += " (stale, refreshing)"
        else:
            subtitle += " (stale, refresh unavailable)"
    return output.Response(
        items=[
            output.Item(
                uid=f"currency:{query.source}:{query.target}",
                title=(
                    f"{_format_decimal(query.amount)} "
                    f"{query.source.upper()} = "
                    f"{converted} {query.target.upper()}"
                ),
                subtitle=subtitle,
                arg=converted,
                autocomplete=f"{converted} {query.target.upper()}",
                icon="icons/dollars17.png",
            )
        ],
        skipknowledge=True,
    )


def updating_response(base):
    return output.Response(
        items=[
            output.Item(
                title="Currency rates updating",
                subtitle=f"Fetching {base.upper()} rates. Try again shortly.",
                valid=False,
                icon="icons/dollars17.png",
            )
        ],
        skipknowledge=True,
        rerun=1,
    )


def unavailable_response(base):
    return output.Response(
        items=[
            output.Item(
                title="Currency rates unavailable",
                subtitle=(
                    f"Could not start background update for "
                    f"{base.upper()}."
                ),
                valid=False,
                icon="icons/dollars17.png",
            )
        ],
        skipknowledge=True,
    )


def convert_query(base_dir, query_text, today=None):
    query = parse_query(query_text)
    if query is None:
        return None

    cache = read_rate_cache(base_dir, query.source)
    if cache is None:
        status = start_background_refresh_status(base_dir, query.source)
        if status == BACKGROUND_REFRESH_FAILED:
            return unavailable_response(query.source)
        return updating_response(query.source)

    today = today or dt.date.today()
    if cache.is_fresh(today):
        return _conversion_response(query, cache, stale=False)

    status = start_background_refresh_status(base_dir, query.source)
    return _conversion_response(
        query,
        cache,
        stale=True,
        refresh_launched=status != BACKGROUND_REFRESH_FAILED,
    )


def is_update_command(query):
    parts = str(query).split()
    return bool(parts and parts[0] == "currency-update")


def manual_refresh_rates(base_dir, base):
    normalized_base = normalize_base(base)
    lock = acquire_refresh_lock(base_dir, normalized_base)
    if not lock.acquired:
        return None
    return _refresh_rates_with_lock(base_dir, normalized_base, lock)


def update_command(base_dir, query):
    match = UPDATE_RE.match(query)
    if match is None:
        return output.Response(
            items=[
                output.Item(
                    title="Invalid currency update command",
                    subtitle="Use currency-update or currency-update <base>.",
                    valid=False,
                    icon="icons/dollars17.png",
                )
            ],
            skipknowledge=True,
        )

    base = (match.group("base") if match and match.group("base") else "eur")
    base = base.lower()
    try:
        cache = manual_refresh_rates(base_dir, base)
    except Exception as error:
        return output.Response(
            items=[
                output.Item(
                    title="Currency update failed",
                    subtitle=str(error),
                    valid=False,
                    icon="icons/dollars17.png",
                )
            ],
            skipknowledge=True,
        )

    if cache is None:
        return output.Response(
            items=[
                output.Item(
                    title="Currency update already running",
                    subtitle=(
                        f"{base.upper()} rates are already refreshing. "
                        "Try again shortly."
                    ),
                    valid=False,
                    icon="icons/dollars17.png",
                )
            ],
            skipknowledge=True,
        )

    return output.Response(
        items=[
            output.Item(
                title=f"Updated {base.upper()} currency rates",
                subtitle=(
                    f"Rates from {cache.date.isoformat()}, "
                    f"{len(cache.rates)} currencies"
                ),
                valid=False,
                icon="icons/dollars17.png",
            )
        ],
        skipknowledge=True,
    )


def cache_root(base_dir=None):
    root = base_dir or os.environ.get("alfred_workflow_cache") or os.getcwd()
    return os.path.join(root, "currency")


def normalize_base(base):
    if not isinstance(base, str):
        raise ValueError("invalid currency base")
    normalized = base.lower()
    if normalized not in CURRENCY_CODES:
        raise ValueError("invalid currency base")
    return normalized


def rate_cache_path(base_dir, base):
    return os.path.join(cache_root(base_dir), f"{normalize_base(base)}.json")


def _lock_path(base_dir, base):
    return os.path.join(
        cache_root(base_dir),
        "locks",
        f"{normalize_base(base)}.lock",
    )


def _lock_metadata_filenames(path):
    return [
        name for name in os.listdir(path)
        if name == "metadata.json"
        or (name.startswith("metadata.") and name.endswith(".json"))
        or (name.startswith(".metadata.") and name.endswith(".tmp"))
    ]


def _path_matches_cleanup(path, cleanup):
    if cleanup.st_dev is None or cleanup.st_ino is None:
        return True
    try:
        path_stat = os.stat(path)
    except OSError:
        return False
    return (
        path_stat.st_dev == cleanup.st_dev
        and path_stat.st_ino == cleanup.st_ino
    )


def _remove_stale_lock_path(path, cleanup):
    if cleanup.is_directory:
        if not _path_matches_cleanup(path, cleanup):
            return
        for name in cleanup.metadata_filenames:
            try:
                os.unlink(os.path.join(path, name))
            except OSError:
                pass
        try:
            os.rmdir(path)
        except OSError:
            pass
        return
    if os.path.isdir(path) or not _path_matches_cleanup(path, cleanup):
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _valid_lock_token(token):
    return isinstance(token, str) and LOCK_TOKEN_RE.match(token) is not None


def _metadata_path(path, token):
    if not _valid_lock_token(token):
        raise ValueError("invalid lock token")
    return os.path.join(path, f"metadata.{token}.json")


def _active_lock_metadata_filename(path):
    filenames = [
        name for name in _lock_metadata_filenames(path)
        if name.startswith("metadata.") and name.endswith(".json")
    ]
    if len(filenames) != 1:
        raise ValueError("lock metadata must be unique")
    return filenames[0]


def _read_lock_metadata_file(path, filename):
    with open(os.path.join(path, filename), "r", encoding="utf-8") as fh:
        metadata = json.load(fh)
    if not isinstance(metadata, dict):
        raise ValueError("lock metadata must be a mapping")
    return metadata


def _read_lock_metadata(path):
    return _read_lock_metadata_file(
        path,
        _active_lock_metadata_filename(path),
    )


def _metadata_created_at(metadata):
    created_at = dt.datetime.fromisoformat(metadata["created_at"])
    if created_at.tzinfo is None:
        raise ValueError("lock metadata timestamp must be timezone-aware")
    token = metadata["token"]
    if not _valid_lock_token(token):
        raise ValueError("lock metadata token is invalid")
    return created_at


def _lock_mtime_is_stale(path, stale_after):
    modified_at = dt.datetime.fromtimestamp(
        os.path.getmtime(path),
        dt.timezone.utc,
    )
    age = dt.datetime.now(dt.timezone.utc) - modified_at
    return age > stale_after


def _path_cleanup_plan(path_stat):
    is_directory = stat.S_ISDIR(path_stat.st_mode)
    return _StaleLockCleanup(
        is_directory=is_directory,
        st_dev=path_stat.st_dev,
        st_ino=path_stat.st_ino,
    )


def _directory_cleanup_plan(path, path_stat, metadata_filenames):
    return _StaleLockCleanup(
        is_directory=True,
        metadata_filenames=tuple(metadata_filenames),
        st_dev=path_stat.st_dev,
        st_ino=path_stat.st_ino,
    )


def _stale_lock_cleanup(path, stale_after):
    try:
        path_stat = os.stat(path)
    except OSError:
        return _StaleLockCleanup(is_directory=False)
    if not stat.S_ISDIR(path_stat.st_mode):
        return _path_cleanup_plan(path_stat)

    try:
        metadata_filename = _active_lock_metadata_filename(path)
        metadata = _read_lock_metadata_file(path, metadata_filename)
        created_at = _metadata_created_at(metadata)
        age = dt.datetime.now(dt.timezone.utc) - created_at
        if age > stale_after:
            return _directory_cleanup_plan(
                path,
                path_stat,
                (metadata_filename,),
            )
        return None
    except (OSError, ValueError, KeyError, TypeError):
        try:
            is_stale = _lock_mtime_is_stale(path, stale_after)
        except OSError:
            return _directory_cleanup_plan(path, path_stat, ())
        if not is_stale:
            return None
        try:
            metadata_filenames = _lock_metadata_filenames(path)
        except OSError:
            metadata_filenames = ()
        return _directory_cleanup_plan(
            path,
            path_stat,
            metadata_filenames,
        )


def _lock_token_matches(path, token):
    if not _valid_lock_token(token):
        return False
    try:
        metadata = _read_lock_metadata(path)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return metadata.get("token") == token


def _remove_owned_lock_metadata(path, token):
    try:
        os.unlink(_metadata_path(path, token))
        return True
    except (OSError, ValueError):
        return False


def _write_lock_metadata(path, token):
    metadata = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "token": token,
    }
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=path,
            prefix=f".metadata.{token}.",
            suffix=".tmp",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, sort_keys=True)
        os.replace(tmp_path, _metadata_path(path, token))
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _new_lock(path):
    token = uuid.uuid4().hex
    created_stat = os.stat(path)
    try:
        _write_lock_metadata(path, token)
    except Exception:
        try:
            current_stat = os.stat(path)
            if (
                current_stat.st_ino == created_stat.st_ino
                and current_stat.st_dev == created_stat.st_dev
            ):
                os.rmdir(path)
        except OSError:
            pass
        raise
    return RefreshLock(path=path, acquired=True, token=token)


def acquire_refresh_lock(base_dir, base, stale_after=None):
    normalized_base = normalize_base(base)
    if stale_after is None:
        stale_after = DEFAULT_LOCK_STALE_AFTER
    path = _lock_path(base_dir, normalized_base)
    with _lock_path_mutex(path):
        try:
            os.mkdir(path)
            return _new_lock(path)
        except FileExistsError:
            cleanup = _stale_lock_cleanup(path, stale_after)
            if cleanup is None:
                return RefreshLock(path=path, acquired=False)
            _remove_stale_lock_path(path, cleanup)

        try:
            os.mkdir(path)
            return _new_lock(path)
        except FileExistsError:
            return RefreshLock(path=path, acquired=False)


def _load_json_url(url, timeout=10):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "alfred-converter/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _rate_cache_from_payload(base, data):
    if not isinstance(data, dict):
        raise ValueError("provider payload must be a mapping")

    date = dt.date.fromisoformat(data["date"])
    rates = data[base]
    parsed_rates = _normalize_rates(
        rates,
        key_error_message="provider rate key is invalid",
        value_error_message="provider rates must be finite",
    )

    return RateCache(
        base=base,
        date=date,
        fetched_at=dt.date.today(),
        rates=parsed_rates,
    )


def fetch_rates(base):
    normalized_base = normalize_base(base)
    errors = []

    for pattern in (PRIMARY_URL, FALLBACK_URL):
        url = pattern.format(currency=normalized_base)
        try:
            data = _load_json_url(url)
            return _rate_cache_from_payload(normalized_base, data)
        except (
            OSError, ValueError, KeyError, TypeError,
            decimal.InvalidOperation,
        ) as error:
            errors.append(error)

    raise RuntimeError(
        f"Unable to fetch rates for {normalized_base}: {errors[-1]}"
    )


def _refresh_rates_with_lock(base_dir, base, lock):
    try:
        cache = fetch_rates(base)
        write_rate_cache(base_dir, cache)
        return cache
    finally:
        lock.release()


def refresh_rates(base_dir, base):
    normalized_base = normalize_base(base)
    lock = acquire_refresh_lock(base_dir, normalized_base)
    if not lock.acquired:
        cache = read_rate_cache(base_dir, normalized_base)
        if cache is not None:
            return cache
        raise RuntimeError(f"Unable to acquire refresh lock for {base}")
    return _refresh_rates_with_lock(base_dir, normalized_base, lock)


def refresh_rates_with_existing_lock(base_dir, base, lock_path, token=None):
    normalized_base = normalize_base(base)
    expected_path = os.path.abspath(_lock_path(base_dir, normalized_base))
    actual_path = os.path.abspath(lock_path)
    if actual_path != expected_path:
        raise ValueError("invalid refresh lock path")
    if not os.path.isdir(actual_path):
        raise ValueError("missing refresh lock")
    if not _lock_token_matches(actual_path, token):
        raise ValueError("invalid refresh lock token")
    lock = RefreshLock(path=actual_path, acquired=True, token=token)
    return _refresh_rates_with_lock(base_dir, normalized_base, lock)


def start_background_refresh_status(base_dir, base):
    normalized_base = normalize_base(base)
    lock = acquire_refresh_lock(base_dir, normalized_base)
    if not lock.acquired:
        return BACKGROUND_REFRESH_ALREADY_RUNNING

    command = [
        sys.executable,
        "-m",
        "converter.currency",
        "update-locked",
        normalized_base,
        lock.path,
    ]
    env = os.environ.copy()
    env[LOCK_TOKEN_ENV] = lock.token
    if base_dir is not None:
        env["alfred_workflow_cache"] = os.fspath(base_dir)

    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "env": env,
    }

    try:
        subprocess.Popen(command, **popen_kwargs)
    except OSError:
        lock.release()
        return BACKGROUND_REFRESH_FAILED
    return BACKGROUND_REFRESH_STARTED


def start_background_refresh(base_dir, base):
    return (
        start_background_refresh_status(base_dir, base)
        == BACKGROUND_REFRESH_STARTED
    )


def read_rate_cache(base_dir, base):
    try:
        normalized_base = normalize_base(base)
        path = rate_cache_path(base_dir, normalized_base)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data["base"] != normalized_base:
            return None
        rates = _normalize_rates(
            data["rates"],
            key_error_message="cache rate key is invalid",
            value_error_message="cache rates must be finite",
        )
        return RateCache(
            base=data["base"],
            date=dt.date.fromisoformat(data["date"]),
            fetched_at=dt.date.fromisoformat(
                data.get("fetched_at", data["date"])
            ),
            rates=rates,
        )
    except (
        AttributeError, OSError, ValueError, KeyError, TypeError,
        decimal.InvalidOperation,
    ):
        return None


def write_rate_cache(base_dir, cache):
    root = cache_root(base_dir)
    os.makedirs(root, exist_ok=True)
    base = normalize_base(cache.base)
    path = rate_cache_path(base_dir, base)
    tmp_path = None
    rates = _normalize_rates(
        cache.rates,
        key_error_message="cache rate key is invalid",
        value_error_message="cache rates must be finite",
    )
    data = {
        "base": base,
        "date": cache.date.isoformat(),
        "fetched_at": cache.fetched_at.isoformat(),
        "rates": {
            key: str(value)
            for key, value in sorted(rates.items())
        },
    }
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=root, prefix=f".{base}.", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    argv = list(argv)
    if len(argv) == 2 and argv[0] == "update":
        refresh_rates(None, argv[1])
        return 0
    if len(argv) == 3 and argv[0] == "update-locked":
        refresh_rates_with_existing_lock(
            None,
            argv[1],
            argv[2],
            token=os.environ.get(LOCK_TOKEN_ENV),
        )
        return 0
    raise SystemExit(
        "Usage: python -m converter.currency update <base> | "
        "update-locked <base> <lock-path>"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
