"""Build the ``/api/history`` payload from database rows.

This module owns the **shape** of the history response and the SQL needed to
produce it. It is deliberately free of Redis, Flask-Caching and HTTP concerns,
so it can be unit-tested without a database server and reused by both the sync
(Flask) and async (FastAPI) code paths.

What belongs here
-----------------
- the time window for a period (``day``, ``week``, ``month``, ``year``),
- the SELECT statement that reads measurements, stations and pollutants,
- grouping, aggregation, downsampling and AQI enrichment,
- the two builders: sync and async.

What does not belong here
-------------------------
- cache reads and writes (see ``backend/utils/history_cache.py``),
- request parsing and HTTP response headers (see ``backend/routes/``).

Payload shape
-------------
::

    {
        "period": "day",
        "from": "2026-11-15T10:00:00",
        "to": "2026-11-16T10:00:00",
        "stations": {
            "E403": {
                "info": {
                    "station_id": "E403",
                    "station_name": "Ljubljana Bežigrad",
                    "latitude": 46.0658,
                    "longitude": 14.5125
                },
                "measurements_list": [
                    {
                        "station_id": "E403",
                        "station_name": "Ljubljana Bežigrad",
                        "time_to": "2026-11-16T09:00:00",
                        "pm10": 21.5,
                        "no2": 14.0
                    }
                ],
                "total_points": 24
            }
        }
    }

``total_points`` is the number of **raw** time points for the station.
``measurements_list`` may contain fewer entries because values are aggregated
into time buckets and optionally downsampled.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.agregation import (
    MAX_POINTS_BY_PERIOD,
    _aggregate_measurements_by_period,
    _downsample_measurements,
)
from backend.analytics.aqi import _attach_aqi_indices
from backend.database.db_models import (
    DbModelMeasurement,
    DbModelPollutant,
    DbModelStation,
)
from backend.database.session import SessionLocal


#: Periods accepted by the API. Kept here because the rolling window and the
#: bucket sizes are defined in this module and in ``backend.analytics``.
ALLOWED_PERIODS = ('day', 'week', 'month', 'year')


def _period_start(period: str) -> datetime:
    """Return the lower bound of the rolling window for ``period``.

    The windows are rolling, not calendar-aligned: ``day`` means "the last
    24 hours", not "since midnight". This matches how the frontend renders
    the charts.

    Args:
        period: One of ``day``, ``week``, ``month``, ``year``.

    Returns:
        Naive ``datetime`` marking the start of the window.

    Raises:
        ValueError: If ``period`` is not one of ``ALLOWED_PERIODS``.

    Note:
        The returned value is naive today. Phase 3 (TimescaleDB +
        ``timestamptz``) changes this to aware UTC.
    """
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


def _history_query(
    start_ts: datetime,
    end_ts: datetime,
    station_id_filter: str | None = None,
) -> Select:
    """Build the SELECT that reads one history window.

    The statement is returned **unexecuted** on purpose: the same ``Select``
    can be run by a sync ``Session`` and an async ``AsyncSession``. This is the
    seam that Phase 3 replaces with a TimescaleDB ``time_bucket`` query.

    Args:
        start_ts: Inclusive lower bound for ``measurements.measured_at``.
        end_ts: Inclusive upper bound for ``measurements.measured_at``.
        station_id_filter: Optional ARSO station code (for example ``E403``).
            Filtering happens in SQL, not in Python.

    Returns:
        A ``Select`` yielding ``(station, measurement, pollutant)`` rows,
        ordered by station code and newest measurement first.
    """
    query = (
        select(DbModelStation, DbModelMeasurement, DbModelPollutant)
        .join(
            DbModelMeasurement,
            DbModelMeasurement.station_id == DbModelStation.id,
        )
        .join(
            DbModelPollutant,
            DbModelPollutant.id == DbModelMeasurement.pollutant_id,
        )
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


def _pivot_rows_by_station_and_time(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """Pivot ``(station, measurement, pollutant)`` rows into per-time dicts.

    Raw measurements are "long" rows: one row per station, pollutant and hour.
    The API payload is "wide": one dict per station and time, with pollutant
    names as keys. This function performs that pivot.

    Args:
        rows: Rows from :func:`_history_query`; each row unpacks into
            ``(station, measurement, pollutant)``.

    Returns:
        Mapping ``station_id -> {"info": {...}, "by_time": {iso_time: {...}}}``.
        ``by_time`` values already contain all pollutants measured at that
        timestamp.
    """
    stations: dict[str, dict[str, Any]] = {}

    for station, measurement, pollutant in rows:
        station_key = station.station_id
        station_entry = stations.setdefault(
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
        time_entry = station_entry['by_time'].setdefault(
            iso_time,
            {
                'station_id': station.station_id,
                'station_name': station.station_name,
                'time_to': iso_time,
            },
        )
        time_entry[pollutant.name] = measurement.value

    return stations


def _finalize_station(
    station_data: dict[str, Any],
    period: str,
) -> dict[str, Any]:
    """Aggregate and enrich one station's raw measurements.

    Steps:
        1. sort measurements newest first,
        2. average values inside period-dependent time buckets,
        3. downsample as a safety net for oversized payloads,
        4. attach EU and WHO AQI indices to every point.

    Args:
        station_data: One value from :func:`_pivot_rows_by_station_and_time`.
        period: Period used to choose the bucket size.

    Returns:
        ``{"info": ..., "measurements_list": [...], "total_points": n}``,
        where ``total_points`` counts raw points before aggregation.
    """
    by_time = station_data['by_time']
    raw_measurements = sorted(
        by_time.values(),
        key=lambda item: item.get('time_to', ''),
        reverse=True,
    )

    aggregated_measurements = _aggregate_measurements_by_period(
        raw_measurements, period
    )
    max_points = MAX_POINTS_BY_PERIOD.get(period, 500)
    measurements_list = _downsample_measurements(
        aggregated_measurements, max_points
    )
    measurements_list = _attach_aqi_indices(measurements_list)

    return {
        'info': station_data['info'],
        'measurements_list': measurements_list,
        'total_points': len(by_time),
    }


def _build_history_payload(
    rows: list[Any],
    period: str,
    start_ts: datetime,
    end_ts: datetime,
) -> dict:
    """Transform database rows into the history API payload.

    Pure function: no database, no cache, no Flask. Both the sync and async
    builders call it, which guarantees that they return an identical shape.

    Args:
        rows: Raw rows from :func:`_history_query`.
        period: One of ``ALLOWED_PERIODS``.
        start_ts: Window start, echoed as ``from`` in the payload.
        end_ts: Window end, echoed as ``to`` in the payload.

    Returns:
        JSON-serializable history payload (see the module docstring).
    """
    stations = _pivot_rows_by_station_and_time(rows)

    payload_stations = {
        station_key: _finalize_station(station_data, period)
        for station_key, station_data in stations.items()
    }

    return {
        'period': period,
        'from': start_ts.isoformat(),
        'to': end_ts.isoformat(),
        'stations': payload_stations,
    }


def filter_history_payload(
    payload: dict[str, Any],
    station_id_filter: str | None,
) -> dict[str, Any]:
    """Return ``payload`` limited to one station.

    The cache stores a single payload for all stations, so station filtering
    happens in memory after reading the cache. Unknown station codes produce a
    payload with an empty ``stations`` mapping rather than an error.

    Args:
        payload: Full history payload.
        station_id_filter: ARSO station code, or ``None`` for no filtering.

    Returns:
        The original object when no filter is given, otherwise a shallow copy
        with ``stations`` reduced to the requested station.
    """
    if not station_id_filter:
        return payload

    stations = payload.get('stations', {})
    station_payload = stations.get(station_id_filter)
    filtered_payload = dict(payload)
    filtered_payload['stations'] = (
        {station_id_filter: station_payload} if station_payload else {}
    )
    return filtered_payload


def build_history_payload_from_db(
    period: str,
    station_id_filter: str | None = None,
) -> dict:
    """Build the history payload using a synchronous session.

    Used by the Flask API and by the hourly cache refresh job. The session is
    created and closed here because the caller has no session of its own.

    Args:
        period: One of ``ALLOWED_PERIODS``.
        station_id_filter: Optional ARSO station code.

    Returns:
        History payload for the requested window.

    Raises:
        ValueError: If ``period`` is invalid.
        sqlalchemy.exc.SQLAlchemyError: If the query fails.
    """
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
    """Build the history payload using an injected async session.

    Used by the FastAPI ``/api/history`` fallback when Redis is empty or down.
    The session is **not** opened or closed here: FastAPI's ``Depends(get_db)``
    owns its lifecycle and closes it after the request.

    Args:
        db: Open ``AsyncSession``.
        period: One of ``ALLOWED_PERIODS``.
        station_id_filter: Optional ARSO station code.

    Returns:
        Same payload shape as :func:`build_history_payload_from_db`.

    Raises:
        ValueError: If ``period`` is invalid.
        sqlalchemy.exc.SQLAlchemyError: If the query fails.
    """
    start_ts = _period_start(period)
    end_ts = datetime.now()
    result = await db.execute(
        _history_query(start_ts, end_ts, station_id_filter)
    )
    rows = result.all()
    return _build_history_payload(rows, period, start_ts, end_ts)


__all__ = [
    'ALLOWED_PERIODS',
    'build_history_payload_from_db',
    'build_history_payload_from_db_async',
    'filter_history_payload',
]
