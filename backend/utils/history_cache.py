"""Read-through cache for the ``/api/history`` payload.

This module owns **caching only**. Building the payload from database rows
lives in ``backend/utils/history_payload.py``; request handling lives in
``backend/routes/``.

Backends
--------
Two optional cache backends are supported, in priority order:

1. **Redis** via ``app.extensions["redis_client"]``. This is the normal
   production path and the same store the hourly update cycle writes to.
2. **Flask-Caching** via ``app.extensions["cache"]`` or ``app.cache``. Used by
   deployments that run Flask without Redis.

Outside a Flask application context both lookups return ``None``. Cache reads
then return ``None`` and writes return ``False``; the API still works, it just
rebuilds from the database.

Keys
----
``history_payload:{period}`` stores the payload for **all** stations. Station
filtering happens in memory after reading, so one key serves every
``?station_id=`` request.

Public API
----------
- :func:`cache_history_payload` — write a payload for one period.
- :func:`get_cached_history_payload` — read and optionally filter a payload.
- :func:`get_history_payload` — read-through: cache, then database, then
  best-effort write-back.
- :func:`refresh_history_cache` — rebuild every period (hourly job).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from flask import current_app

from backend.utils.history_payload import *
from backend.utils.serialization import to_serializable


#: Prefix for every history payload key. Kept stable so the Flask API, the
#: FastAPI API and the update job all read and write the same entries.
HISTORY_CACHE_KEY_PREFIX = 'history_payload:'


def _get_redis_client() -> Optional[Any]:
    """Return the Flask app's Redis client, or ``None`` if unavailable.

    The client is registered by ``backend/app.py`` in
    ``app.extensions["redis_client"]``. Accessing ``current_app`` outside an
    application context raises ``RuntimeError``; that is treated as "no cache",
    not as an error, because cache use is optional.
    """
    try:
        app = current_app
    except RuntimeError:
        return None

    if app and getattr(app, 'extensions', None):
        return app.extensions.get('redis_client')
    return None


def _get_cache_client() -> Optional[Any]:
    """Return the Flask-Caching instance, or ``None`` if unavailable.

    Supports both registration styles used across Flask versions:
    ``app.extensions["cache"]`` and an ``app.cache`` attribute.
    """
    try:
        app = current_app
    except RuntimeError:
        return None

    if app and getattr(app, 'extensions', None):
        cache = app.extensions.get('cache')
        if cache:
            return cache

    if app and hasattr(app, 'cache'):
        return getattr(app, 'cache')
    return None


def _cache_clients() -> list[tuple[str, Any]]:
    """Return available cache clients in priority order.

    Returns:
        List of ``(backend_name, client)`` pairs. The name is only used in log
        messages. The list is empty when running outside a Flask app context.
    """
    clients: list[tuple[str, Any]] = []

    redis_client = _get_redis_client()
    if redis_client is not None:
        clients.append(('redis', redis_client))

    cache_ext = _get_cache_client()
    if cache_ext is not None:
        clients.append(('cache', cache_ext))

    return clients


def _cache_key(period: str) -> str:
    """Return the cache key for ``period``.

    Example:
        ``_cache_key("day")`` -> ``"history_payload:day"``.
    """
    return f'{HISTORY_CACHE_KEY_PREFIX}{period}'


def _serialize_payload(payload: dict[str, Any]) -> str:
    """Serialize a payload to JSON, handling ``datetime`` values.

    ``to_serializable`` converts dates and other non-JSON Python objects to
    strings so the payload can be stored in Redis as-is.
    """
    return json.dumps(payload, default=to_serializable, ensure_ascii=False)


def _deserialize_payload(raw_payload: object) -> Optional[dict[str, Any]]:
    """Turn a cached value into a payload dict, or ``None`` if unusable.

    Accepts bytes (Redis may return bytes), JSON strings and already-decoded
    dicts, because different cache backends return different types.

    Invalid JSON is logged and treated as a cache miss; a corrupt cache entry
    must never break the API.
    """
    if raw_payload is None:
        return None

    if isinstance(raw_payload, bytes):
        raw_payload = raw_payload.decode('utf-8')

    if isinstance(raw_payload, str):
        try:
            parsed = json.loads(raw_payload)
        except Exception:
            logging.exception('Failed to deserialize cached history payload')
            return None

        if isinstance(parsed, dict):
            return parsed

    if isinstance(raw_payload, dict):
        return raw_payload

    return None


def _read_cached_raw_value(cache_key: str) -> object:
    """Read ``cache_key`` from the first backend that has a value.

    Errors are logged and treated as misses so a broken cache backend never
    breaks the API.
    """
    for backend, client in _cache_clients():
        getter = getattr(client, 'get', None)
        if getter is None:
            continue

        try:
            value = getter(cache_key)
        except Exception as e:
            logging.exception(f'Failed to get {cache_key} from {backend}: {e}')
            continue

        if value is not None:
            return value

    return None


def _write_cached_raw_value(cache_key: str, payload_json: str) -> bool:
    """Write ``payload_json`` to the first backend that accepts it.

    Returns:
        ``True`` if at least one backend stored the value, ``False`` otherwise.
        A missing cache is not an error; the caller can still serve the data.
    """
    for backend, client in _cache_clients():
        setter = getattr(client, 'set', None)
        if setter is None:
            continue

        try:
            setter(cache_key, payload_json)
            return True
        except Exception as e:
            logging.exception(f'Failed to write {cache_key} to {backend}: {e}')

    logging.warning(
        f'No cache client available; skipping cache write for {cache_key}.'
    )
    return False


def cache_history_payload(period: str, payload: dict[str, Any]) -> bool:
    """Store one period's payload in the cache.

    Args:
        period: One of ``ALLOWED_PERIODS``.
        payload: Full payload for all stations.

    Returns:
        ``True`` if the payload was stored, ``False`` if no cache backend was
        available or all writes failed.
    """
    return _write_cached_raw_value(_cache_key(period), _serialize_payload(payload))


def get_cached_history_payload(
    period: str,
    station_id_filter: str | None = None,
) -> Optional[dict[str, Any]]:
    """Read one period's payload from the cache.

    Args:
        period: One of ``ALLOWED_PERIODS``.
        station_id_filter: Optional ARSO station code applied in memory.

    Returns:
        The payload, or ``None`` on a cache miss or an unreadable entry.
    """
    cached_payload = _deserialize_payload(
        _read_cached_raw_value(_cache_key(period))
    )
    if cached_payload is None:
        return None

    return filter_history_payload(cached_payload, station_id_filter)


def get_history_payload(
    period: str,
    station_id_filter: str | None = None,
) -> Optional[dict[str, Any]]:
    """Return the history payload, using the cache as a read-through layer.

    Flow:
        1. Try the cache.
        2. On a miss, build from the database.
        3. Best-effort write the fresh payload back to the cache.
        4. Apply the station filter and return.

    Args:
        period: One of ``ALLOWED_PERIODS``.
        station_id_filter: Optional ARSO station code.

    Returns:
        The payload, or ``None`` if the database build failed.
    """
    cached_payload = get_cached_history_payload(period, station_id_filter)
    if cached_payload is not None:
        return cached_payload

    try:
        payload = build_history_payload_from_db(period, station_id_filter)
    except Exception:
        logging.exception('Failed to build history payload from DB')
        return None

    cache_history_payload(period, payload)
    return filter_history_payload(payload, station_id_filter)


def refresh_history_cache(
    periods: tuple[str, ...] = ALLOWED_PERIODS,
) -> bool:
    """Rebuild and store the payload for every period.

    Called by the hourly update cycle after new measurements are inserted.
    A failure for one period does not stop the others.

    Args:
        periods: Periods to refresh; defaults to all allowed periods.

    Returns:
        ``True`` only if every period was built and stored successfully.
    """
    success = True

    for period in periods:
        try:
            payload = build_history_payload_from_db(period)
            if not cache_history_payload(period, payload):
                success = False
        except Exception:
            success = False
            logging.exception(
                f'Failed to refresh history cache for period={period}'
            )

    return success

# export stack
__all__ = [
    'ALLOWED_PERIODS',
    'HISTORY_CACHE_KEY_PREFIX',
    'cache_history_payload',
    'get_cached_history_payload',
    'get_history_payload',
    'refresh_history_cache',
]
