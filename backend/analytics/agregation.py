"""
Time-bucket aggregation and downsampling.

Pure functions - no DB, no Redis, no Flask.
Used by build_history_payload_from_db to reduce the number of data points
before sending them to the frontend.

Why aggregate?
    Raw measurements are 1 per hour per pollutant per station.
    A year of data = 8760 points per station. Too much for a chart.
    Aggregation groups them into buckets (1h / 3h / 6h / 24h),
    then averages values within each bucket.

Why downsample?
    Even after aggregation, some periods produce more points than
    the frontend can render. Downsampling reduces to max_points
    while keeping the first and last point.
"""
##########################################################################

from datetime import datetime
from typing import Any
from backend.analytics.utils import _to_float

# Max data points per station, by period.
#
# These values MATCH the aggregation output:
#   day   -> 24h / 1h  = 24
#   week  -> 7d * 24h / 3h = 56
#   month -> 30d * 24h / 6h = 120
#   year  -> 365d * 24h / 24h = 365
#
# Downsample is a SAFETY NET - it should never trigger in normal operation,
# but protects API consumers (mobile app, third-party) from oversized payloads
# if aggregation ever produces more points than expected.
# One point is added to all values to avoid last point to be cut in downsample since first and last point should be kept
#
# Frontend also downsamples (hardcoded 420) - that's a separate safety layer.
# Our limit is lower (24-365) because that's what aggregation naturally produces.
MAX_POINTS_BY_PERIOD: dict[str, int] = {
    'day': 25,
    'week': 57,
    'month': 121,
    'year': 366,
}

def _bucket_seconds_for_period(period: str) -> int:
    """
    Return bucket size in seconds for a given period.

    Args:
        period: 'day', 'week', 'month', or 'year'.

    Returns:
        int: Bucket size in seconds.
            day   -> 3600    (1 hour)
            week  -> 10800   (3 hours)
            month -> 21600   (6 hours)
            year  -> 86400   (24 hours)
    """
    if period == 'day':
        return 3600  # hourly
    if period == 'week':
        return 3 * 3600  # 3-hour bins
    if period == 'month':
        return 6 * 3600  # 6-hour bins
    return 24 * 3600  # daily for year


def _downsample_measurements(
    measurements: list[dict[str, Any]],
    max_points: int,
) -> list[dict[str, Any]]:
    """
    Reduce list to max_points items, evenly spaced.

    Keeps the FIRST and LAST item - critical for charts
    (must show start and end of period).

    Args:
        measurements: List of measurement dicts.
        max_points: Maximum number of items to return.

    Returns:
        list[dict]: Downsampled list (length <= max_points).

    Example:
        100 items, max_points=10:
            step = 100 // 10 = 10
            sampled = [0, 10, 20, ..., 90]          (10 items)
            replace last with data[-1] (99)
            result = [0, 10, 20, ..., 80, 99]       (10 items, last=99)
    """
    if len(measurements) <= max_points:
        return measurements

    step = max(1, len(measurements) // max_points)
    sampled = measurements[::step]

    # Reserve last slot for the real last measurement.
    return sampled[:max_points - 1] + [measurements[-1]]


def _aggregate_measurements_by_period(
    measurements_list: list[dict[str, Any]],
    period: str,
) -> list[dict[str, Any]]:
    """
    Group measurements into time buckets, average values within each bucket.

    Bucket size depends on period:
        day   -> 1 hour  (24 buckets/day)
        week  -> 3 hours (56 buckets/week)
        month -> 6 hours (120 buckets/month)
        year  -> 24 hours (365 buckets/year)

    Args:
        measurements_list: List of measurement dicts, each with 'time_to' ISO string.
        period: 'day', 'week', 'month', or 'year'.

    Returns:
        list[dict]: Aggregated measurements, reverse chronological (newest first).

    Example (day, 1h buckets):
        Input:
            [{time_to: 10:15, pm25: 10}, {time_to: 10:45, pm25: 20}]
        Output:
            [{time_to: 11:00, pm25: 15}]   (both in 10:00-11:00 bucket, avg=15)

    Metadata keys (station_id, station_name, time_to, time_from)
    are preserved as-is. Numeric keys (pollutants) are averaged.
    """
    if not measurements_list:
        return measurements_list

    bucket_seconds = _bucket_seconds_for_period(period)
    metadata_keys = {'station_id', 'station_name', 'time_to', 'time_from'}

    # Sort ascending - so buckets are processed in deterministic order.
    ascending = sorted(measurements_list, key=lambda item: item.get('time_to', ''))
    buckets: dict[int, dict[str, Any]] = {}

    for row in ascending:
        iso_time = row.get('time_to')
        if not iso_time:
            continue
        try:
            dt = datetime.fromisoformat(str(iso_time))
        except Exception:
            continue

        # Round DOWN to bucket boundary.
        # Example (1h bucket): 10:15 and 10:45 both become 10:00.
        epoch = int(dt.timestamp())
        bucket_epoch = (epoch // bucket_seconds) * bucket_seconds

        # Get-or-create bucket. Metadata stays, _sums/_counts are for averaging.
        bucket = buckets.setdefault(
            bucket_epoch,
            {
                'station_id': row.get('station_id'),
                'station_name': row.get('station_name'),
                'time_to': datetime.fromtimestamp(bucket_epoch + bucket_seconds).isoformat(),
                '_sums': {},
                '_counts': {},
            },
        )

        # Accumulate sums and counts for each pollutant.
        for key, value in row.items():
            if key in metadata_keys:
                continue
            numeric = _to_float(value)
            if numeric is None:
                continue
            bucket['_sums'][key] = bucket['_sums'].get(key, 0.0) + numeric
            bucket['_counts'][key] = bucket['_counts'].get(key, 0) + 1

    # Average sums/counts, drop internal fields.
    aggregated: list[dict[str, Any]] = []
    for bucket_epoch in sorted(buckets.keys()):
        bucket = buckets[bucket_epoch]
        row: dict[str, Any] = {
            'station_id': bucket.get('station_id'),
            'station_name': bucket.get('station_name'),
            'time_to': bucket.get('time_to'),
        }
        sums = bucket.get('_sums', {})
        counts = bucket.get('_counts', {})
        for pollutant_key, total in sums.items():
            count = counts.get(pollutant_key, 0)
            if count > 0:
                row[pollutant_key] = round(total / count, 2)
        aggregated.append(row)

    # API expects reverse chronological order (newest first).
    return list(reversed(aggregated))