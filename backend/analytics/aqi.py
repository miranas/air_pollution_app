"""
AQI (Air Quality Index) calculation.

Pure functions - no DB, no Redis, no Flask.
Can be used by both Flask and FastAPI.

AQI is a single number (0-300) that describes air quality:
    0-50    : Good
    51-100  : Moderate
    101-150 : Unhealthy for sensitive groups
    151-300 : Unhealthy (capped at 300)

Two profiles:
    - EU:  less strict (European legislation)
    - WHO: stricter (World Health Organization)
"""
from typing import Any, Optional
from backend.analytics.utils import _to_float


# EU thresholds: (good_max, ok_max, warn_max)
AQI_THRESHOLDS_EU: dict[str, tuple[float, float, float]] = {
    'pm25': (10.0, 20.0, 25.0),
    'pm10': (20.0, 40.0, 50.0),
    'no2': (20.0, 40.0, 60.0),
    'o3': (80.0, 120.0, 180.0),
    'so2': (40.0, 125.0, 350.0),
    'co': (4.0, 7.0, 10.0),
    'nox': (30.0, 60.0, 100.0),
}

# WHO thresholds (stricter than EU)
AQI_THRESHOLDS_WHO: dict[str, tuple[float, float, float]] = {
    'pm25': (5.0, 10.0, 15.0),
    'pm10': (15.0, 30.0, 45.0),
    'no2': (10.0, 25.0, 40.0),
    'o3': (50.0, 80.0, 120.0),
    'so2': (20.0, 40.0, 80.0),
    'co': (2.0, 4.0, 8.0),
    'nox': (20.0, 40.0, 80.0),
}


def _to_aqi_band_score(value: float, thresholds: tuple[float, float, float]) -> int:
    """
    Convert raw pollutant value to AQI score (0-300).

    Args:
        value: Raw pollutant value (e.g., PM2.5 in µg/m³).
        thresholds: (good_max, ok_max, warn_max) for this pollutant.

    Returns:
        int: AQI score 0-300.

    Bands:
        0-50    : value <= good_max
        51-100  : good_max < value <= ok_max
        101-150 : ok_max < value <= warn_max
        151-300 : value > warn_max (capped at 300 if value >= 2*warn_max)
    """
    good_max, ok_max, warn_max = thresholds

    if value <= good_max:
        return round((value / good_max) * 50)
    if value <= ok_max:
        return round(51 + ((value - good_max) / (ok_max - good_max)) * 49)
    if value <= warn_max:
        return round(101 + ((value - ok_max) / (warn_max - ok_max)) * 49)

    hard_cap = warn_max * 2
    if value >= hard_cap:
        return 300
    return round(151 + ((value - warn_max) / (hard_cap - warn_max)) * 149)


def _compute_aqi_index(measurement: dict[str, Any], profile: str) -> Optional[int]:
    """
    Compute AQI for a measurement = MAX score across all pollutants.

    Args:
        measurement: Dict with pollutant values (e.g., {'pm25': 15, 'no2': 40}).
        profile: 'eu' or 'who' (which thresholds to use).

    Returns:
        int or None: MAX AQI across pollutants, or None if no numeric values.
    """
    thresholds_map = AQI_THRESHOLDS_WHO if profile == 'who' else AQI_THRESHOLDS_EU
    max_score: Optional[int] = None

    for pollutant_key, thresholds in thresholds_map.items():
        numeric_value = _to_float(measurement.get(pollutant_key))
        if numeric_value is None:
            continue
        score = _to_aqi_band_score(numeric_value, thresholds)
        if max_score is None or score > max_score:
            max_score = score

    return max_score


def _attach_aqi_indices(measurements_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Add aqi_eu and aqi_who to each measurement in the list.

    Args:
        measurements_list: List of measurement dicts.

    Returns:
        list[dict]: New list with 'aqi_eu' and 'aqi_who' added to each item.
    """
    enriched: list[dict[str, Any]] = []
    for item in measurements_list:
        row = dict(item)
        row['aqi_eu'] = _compute_aqi_index(row, 'eu')
        row['aqi_who'] = _compute_aqi_index(row, 'who')
        enriched.append(row)
    return enriched