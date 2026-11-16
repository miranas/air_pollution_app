from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import Any, Optional
from flask import current_app
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.agregation import (
     MAX_POINTS_BY_PERIOD,
    _aggregate_measurements_by_period,
    _downsample_measurements,
)

from backend.database.db_models import DbModelMeasurement, DbModelPollutant, DbModelStation
from backend.database.session import SessionLocal
from backend.utils.serialization import to_serializable




from backend.analytics.aqi import (
    AQI_THRESHOLDS_EU,
    AQI_THRESHOLDS_WHO,
    _attach_aqi_indices,
    _compute_aqi_index,
    _to_aqi_band_score,
    _to_float,
)


HISTORY_CACHE_KEY_PREFIX = 'history_payload:'
ALLOWED_PERIODS = ('day', 'week', 'month', 'year')


def _period_start(period: str) -> datetime:
    now = datetime.now()
    if period == 'day':
        return now - timedelta(days=1)
    if period == 'week':
        return now - timedelta(weeks=1)
    if period == 'month':
        return now - timedelta(days=30)
    if period == 'year':
        return now - timedelta(days=365)
    raise ValueError('Invalid period')


def _get_redis_client() -> Optional[Any]:
    try:
        app = current_app
    except RuntimeError:
        return None

    if app and getattr(app, 'extensions', None):
        return app.extensions.get('redis_client')
    return None


def _get_cache_client() -> Optional[Any]:
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


def _cache_key(period: str) -> str:
    return f'{HISTORY_CACHE_KEY_PREFIX}{period}'


def _serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=to_serializable, ensure_ascii=False)


def _deserialize_payload(raw_payload: object) -> Optional[dict[str, Any]]:
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
    cached = None
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
        except Exception as e:
            logging.exception(f'Failed to get {cache_key} from redis: {e}')

    if cached is None:
        cache_ext = _get_cache_client()
        if cache_ext and hasattr(cache_ext, 'get'):
            try:
                cached = cache_ext.get(cache_key)
            except Exception as e:
                logging.exception(f'Failed to get {cache_key} from cache: {e}')

    return cached


def _write_cached_raw_value(cache_key: str, payload_json: str) -> bool:
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_client.set(cache_key, payload_json)
            return True
        except Exception as e:
            logging.exception(f'Failed to write {cache_key} to redis: {e}')

    cache_ext = _get_cache_client()
    if cache_ext and hasattr(cache_ext, 'set'):
        try:
            cache_ext.set(cache_key, payload_json)
            return True
        except Exception as e:
            logging.exception(f'Failed to write {cache_key} to cache: {e}')

    logging.warning(f'No cache client available; skipping cache write for {cache_key}.')
    return False


def _filter_history_payload(payload: dict[str, Any], station_id_filter: str | None) -> dict[str, Any]:
    if not station_id_filter:
        return payload

    stations = payload.get('stations', {})
    station_payload = stations.get(station_id_filter)
    filtered_payload = dict(payload)
    filtered_payload['stations'] = {station_id_filter: station_payload} if station_payload else {}
    return filtered_payload


def _history_query(
    start_ts: datetime,
    end_ts: datetime,
    station_id_filter: str | None = None,
):
    """Build the SELECT used by both sync and async history builders.

    Kept separate from the session so the same statement works with
    ``Session`` and ``AsyncSession``.
    """
    query = (
        select(DbModelStation, DbModelMeasurement, DbModelPollutant)
        .join(DbModelMeasurement, DbModelMeasurement.station_id == DbModelStation.id)
        .join(DbModelPollutant, DbModelPollutant.id == DbModelMeasurement.pollutant_id)
        .where(DbModelMeasurement.measured_at >= start_ts)
        .where(DbModelMeasurement.measured_at <= end_ts)
        .order_by(
            DbModelStation.station_id.asc(),
            DbModelMeasurement.measured_at.desc(),
        )
    )

    if station_id_filter:
        query = query.where(DbModelStation.station_id == station_id_filter)

    return query


def _build_history_payload(
    rows: list[Any],
    period: str,
    start_ts: datetime,
    end_ts: datetime,
) -> dict:
    """Transform DB rows into the history API payload.

    Pure function: no database, no cache, no Flask. Both the sync and async
    builders call it, so the output shape stays identical.
    """
    stations: dict[str, dict[str, Any]] = {}
    for station, measurement, pollutant in rows:
        station_key = station.station_id
        station_bucket = stations.setdefault(
            station_key,
            {
                'info': {
                    'station_id': station.station_id,
                    'station_name': station.station_name,
                    'latitude': station.latitude,
                    'longitude': station.longitude,
                },
                'by_time': {},
            },
        )

        iso_time = measurement.measured_at.isoformat()
        time_bucket = station_bucket['by_time'].setdefault(
            iso_time,
            {
                'station_id': station.station_id,
                'station_name': station.station_name,
                'time_to': iso_time,
            },
        )
        time_bucket[pollutant.name] = measurement.value

    max_points_per_station = MAX_POINTS_BY_PERIOD.get(period, 500)
    payload_stations: dict[str, dict[str, Any]] = {}
    for station_key, station_data in stations.items():
        by_time = station_data['by_time']
        raw_measurements = sorted(
            by_time.values(),
            key=lambda item: item.get('time_to', ''),
            reverse=True,
        )

        aggregated_measurements = _aggregate_measurements_by_period(raw_measurements, period)
        measurements_list = _downsample_measurements(aggregated_measurements, max_points_per_station)
        measurements_list = _attach_aqi_indices(measurements_list)

        payload_stations[station_key] = {
            'info': station_data['info'],
            'measurements_list': measurements_list,
            'total_points': len(by_time),
        }

    return {
        'period': period,
        'from': start_ts.isoformat(),
        'to': end_ts.isoformat(),
        'stations': payload_stations,
    }


def build_history_payload_from_db(period: str, station_id_filter: str | None = None) -> dict:
    """Sync history builder used by Flask and the cache refresh job."""
    db = SessionLocal()
    try:
        start_ts = _period_start(period)
        end_ts = datetime.now()
        rows = db.execute(
            _history_query(start_ts, end_ts, station_id_filter)
        ).all()
        return _build_history_payload(rows, period, start_ts, end_ts)
    finally:
        db.close()


async def build_history_payload_from_db_async(
    db: AsyncSession,
    period: str,
    station_id_filter: str | None = None,
) -> dict:
    """Async history builder used by the FastAPI fallback.

    Takes an already-open AsyncSession (injected via Depends(get_db)) and
    returns exactly the same payload shape as the sync builder.
    """
    start_ts = _period_start(period)
    end_ts = datetime.now()
    result = await db.execute(
        _history_query(start_ts, end_ts, station_id_filter)
    )
    rows = result.all()
    return _build_history_payload(rows, period, start_ts, end_ts)


def cache_history_payload(period: str, payload: dict[str, Any]) -> bool:
    return _write_cached_raw_value(_cache_key(period), _serialize_payload(payload))


def get_cached_history_payload(period: str, station_id_filter: str | None = None) -> Optional[dict[str, Any]]:
    cached_payload = _deserialize_payload(_read_cached_raw_value(_cache_key(period)))
    if cached_payload is None:
        return None

    return _filter_history_payload(cached_payload, station_id_filter)


def get_history_payload(period: str, station_id_filter: str | None = None) -> Optional[dict[str, Any]]:
    cached_payload = get_cached_history_payload(period, station_id_filter)
    if cached_payload is not None:
        return cached_payload

    try:
        payload = build_history_payload_from_db(period, station_id_filter)
    except Exception:
        logging.exception('Failed to build history payload from DB')
        return None

    cache_history_payload(period, payload)
    return _filter_history_payload(payload, station_id_filter)


def refresh_history_cache(periods: tuple[str, ...] = ALLOWED_PERIODS) -> bool:
    success = True
    for period in periods:
        try:
            payload = build_history_payload_from_db(period)
            if not cache_history_payload(period, payload):
                success = False
        except Exception:
            success = False
            logging.exception(f'Failed to refresh history cache for period={period}')
    return success