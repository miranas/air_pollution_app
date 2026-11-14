"""
Tests for backend/utils/history_cache.py

These tests cover pure functions (AQI calculation, aggregation, downsampling)
before we refactor the module. They serve as a safety net.

Test structure:
    - TestAqiBandScore: maps raw value → AQI (0-300), one test per band
    - TestAqiIndex: computes MAX AQI across pollutants (EU/WHO profiles)
    - TestAttachAqiIndices: enriches measurements with aqi_eu/aqi_who
    - TestDownsample: reduces point count, keeps first and last
    - TestAggregate: groups measurements into time buckets, averages
    - TestPeriodStart: returns now - period (1d/7d/30d/365d)

Why 22 tests?
    Each test covers ONE specific behavior. When one fails, you know exactly
    what broke. Tests that cover multiple things at once hide bugs.
"""
import pytest
from datetime import datetime, timedelta

from backend.utils.history_cache import (
    _to_aqi_band_score,
    _compute_aqi_index,
    _attach_aqi_indices,    
    _period_start,
    AQI_THRESHOLDS_EU,
    AQI_THRESHOLDS_WHO,
    
)

from backend.analytics.agregation import(
    MAX_POINTS_BY_PERIOD,
    _downsample_measurements,
    _aggregate_measurements_by_period,   
    
)


# ---------------------------------------------------------------------------
# AQI band score tests
#
# AQI is 0-300, split into 4 bands:
#   0-50    : Good
#   51-100  : Moderate
#   101-150 : Unhealthy for sensitive groups
#   151-300 : Unhealthy (capped at 300)
#
# One test per band + edge cases (zero, hard cap).
# ---------------------------------------------------------------------------

class TestAqiBandScore:
    """Tests for _to_aqi_band_score: raw value → AQI (0-300)."""

    def test_good_band(self):
        """
        Band 1 (Good): 0 ≤ value ≤ good_max.

        PM2.5 = 5 µg/m³, thresholds = (10, 20, 25):
            value ≤ 10 → AQI = (5/10) × 50 = 25
        """
        assert _to_aqi_band_score(5, (10, 20, 25)) == 25

    def test_moderate_band(self):
        """
        Band 2 (Moderate): good_max < value ≤ ok_max.

        PM2.5 = 15 µg/m³, thresholds = (10, 20, 25):
            10 < 15 ≤ 20 → AQI = 51 + ((15-10)/(20-10)) × 49 = 76
        """
        assert _to_aqi_band_score(15, (10, 20, 25)) == 76

    def test_unhealthy_sensitive_band(self):
        """
        Band 3 (Unhealthy for sensitive): ok_max < value ≤ warn_max.

        PM2.5 = 22 µg/m³, thresholds = (10, 20, 25):
            20 < 22 ≤ 25 → AQI = 101 + ((22-20)/(25-20)) × 49 = 121
        """
        assert _to_aqi_band_score(22, (10, 20, 25)) == 121

    def test_unhealthy_band(self):
        """
        Band 4 (Unhealthy): value > warn_max.

        PM2.5 = 30 µg/m³, thresholds = (10, 20, 25):
            30 > 25 → AQI = 151 + ((30-25)/(50-25)) × 149 = 181
        """
        assert _to_aqi_band_score(30, (10, 20, 25)) == 181

    def test_hard_cap(self):
        """
        Hard cap: value ≥ 2 × warn_max → AQI = 300 (max).

        PM2.5 = 50 µg/m³, thresholds = (10, 20, 25):
            50 ≥ 2 × 25 = 50 → AQI = 300
        """
        assert _to_aqi_band_score(50, (10, 20, 25)) == 300

    def test_zero_value(self):
        """
        Edge case: value = 0 → AQI = 0.

        PM2.5 = 0 µg/m³:
            0 ≤ 10 → AQI = (0/10) × 50 = 0
        """
        assert _to_aqi_band_score(0, (10, 20, 25)) == 0


# ---------------------------------------------------------------------------
# AQI index tests (MAX across pollutants)
#
# AQI for a measurement = max AQI across all pollutants present.
# Not sum, not average - MAX. This is the standard AQI definition.
#
# Two profiles: EU (less strict) and WHO (stricter).
# ---------------------------------------------------------------------------

class TestAqiIndex:
    """Tests for _compute_aqi_index: MAX AQI across pollutants."""

    def test_single_pollutant(self):
        """
        Only one pollutant present → its AQI is the result.

        PM2.5 = 15 µg/m³ (EU) → AQI = 76
        """
        measurement = {"pm25": 15}
        assert _compute_aqi_index(measurement, "eu") == 76

    def test_multiple_pollutants_max(self):
        """
        Multiple pollutants → MAX of their AQIs (not sum).

        PM2.5 = 15 → AQI 76
        NO2 = 40 → AQI 100 (at ok_max boundary)
        Result = max(76, 100) = 100
        """
        measurement = {"pm25": 15, "no2": 40}
        assert _compute_aqi_index(measurement, "eu") == 100

    def test_none_only(self):
        """
        Edge case: all values None → return None (no crash).

        This proves None is handled gracefully, not treated as 0.
        """
        assert _compute_aqi_index({"pm25": None, "no2": None}, "eu") is None

    def test_none_values_ignored(self):
        """
        None values are skipped, only present values count.

        pm25 = None (skipped)
        no2 = 40 → AQI 100
        Result = 100 (None doesn't lower or raise the result)
        """
        assert _compute_aqi_index({"pm25": None, "no2": 40}, "eu") == 100

    def test_who_profile(self):
        """
        WHO thresholds are stricter than EU.

        PM2.5 = 15 µg/m³:
            EU thresholds (10, 20, 25)  → AQI 76
            WHO thresholds (5, 10, 15)  → AQI 150 (at warn_max)
        """
        measurement = {"pm25": 15}
        assert _compute_aqi_index(measurement, "who") == 150


# ---------------------------------------------------------------------------
# Attach AQI indices tests
#
# Enriches a measurement list with aqi_eu and aqi_who fields.
# Used by build_history_payload_from_db before returning to the API.
# ---------------------------------------------------------------------------

class TestAttachAqiIndices:
    """Tests for _attach_aqi_indices: adds aqi_eu/aqi_who to each item."""

    def test_attaches_both_indices(self):
        """
        Each measurement gets aqi_eu and aqi_who.

        PM2.5 = 15, NO2 = 40:
            aqi_eu  = max(76, 100) = 100
            aqi_who = max(150, ?) → 150 (PM2.5 dominates)
        """
        measurements = [{"pm25": 15, "no2": 40}]
        result = _attach_aqi_indices(measurements)
        assert result[0]["aqi_eu"] == 100
        assert result[0]["aqi_who"] == 150

    def test_empty_list(self):
        """
        Edge case: empty list → empty list (no crash).
        """
        assert _attach_aqi_indices([]) == []


# ---------------------------------------------------------------------------
# Downsampling tests
#
# Reduces a list to max_points items, evenly spaced.
# Keeps FIRST and LAST item - critical for charts (must show start and end).
# ---------------------------------------------------------------------------

class TestDownsample:
    """Tests for _downsample_measurements: reduce list, keep first + last."""

    def test_no_downsample_needed(self):
        """
        If list is already small enough, return unchanged.

        10 items, max 20 → returns all 10 (10 ≤ 20).
        """
        data = list(range(10))
        assert _downsample_measurements(data, max_points=20) == data

    def test_downsample_evenly(self):
        """
        Reduces list evenly, keeps first and last.

        100 items, max 10:
            step = 100 // 10 = 10
            sampled = [0, 10, 20, ..., 90]  (10 items)
            replace last → [0, 10, ..., 80, 99]  (10 items, last=99)
        """
        data = list(range(100))
        result = _downsample_measurements(data, max_points=10)
        assert len(result) == 10
        assert result[0] == 0
        assert result[-1] == 99

    def test_downsample_keeps_last(self):
        """
        Regression test: last item must never be lost.

        500 items, max 192:
            step = 500 // 192 = 2
            sampled = [0, 2, 4, ..., 498]  (250 items)
            replace last → [0, 2, ..., 498?, 499]  (192 items, last=499)

        Bug history: old code did `sampled.append(last)` then `[:192]`,
        which dropped the last item (returned 382, not 499).
        """
        data = list(range(500))
        result = _downsample_measurements(data, max_points=192)
        assert len(result) <= 192
        assert result[-1] == 499


# ---------------------------------------------------------------------------
# Aggregation by period tests
#
# Groups measurements into time buckets (1h/3h/6h/24h) and averages.
# Example: 2 measurements in same hour → 1 bucket with average value.
# ---------------------------------------------------------------------------

class TestAggregate:
    """Tests for _aggregate_measurements_by_period: group into buckets."""

    def test_empty_list(self):
        """
        Edge case: empty list → empty list (no crash).
        """
        assert _aggregate_measurements_by_period([], "day") == []

    def test_single_measurement(self):
        """
        Single measurement → single bucket, value unchanged.

        1 measurement at 10:00 with pm25=10:
            → 1 bucket at 10:00 with pm25=10
        """
        measurements = [{
            "station_id": "E403",
            "station_name": "LJ Bežigrad",
            "time_to": "2026-11-06T10:00:00",
            "pm25": 10.0,
        }]
        result = _aggregate_measurements_by_period(measurements, "day")
        assert len(result) == 1
        assert result[0]["pm25"] == 10.0

    def test_two_measurements_same_hour(self):
        """
        Two measurements in same 1h bucket → averaged.

        Day period (1h buckets):
            10:15 pm25=10
            10:45 pm25=20
            → 1 bucket at 10:00 with pm25=(10+20)/2=15
        """
        measurements = [
            {"station_id": "E403", "station_name": "LJ", "time_to": "2026-11-06T10:15:00", "pm25": 10.0},
            {"station_id": "E403", "station_name": "LJ", "time_to": "2026-11-06T10:45:00", "pm25": 20.0},
        ]
        result = _aggregate_measurements_by_period(measurements, "day")
        assert len(result) == 1
        assert result[0]["pm25"] == 15.0


# ---------------------------------------------------------------------------
# Period start tests
#
# Returns (now - period) as a datetime.
# Used by build_history_payload_from_db as the lower bound of the DB query.
# ---------------------------------------------------------------------------

class TestPeriodStart:
    """Tests for _period_start: returns now - period as datetime."""

    def test_day(self):
        """
        'day' → now - 1 day (86400 seconds).
        """
        start = _period_start("day")
        now = datetime.now()
        assert abs((now - start).total_seconds() - 86400) < 1

    def test_week(self):
        """
        'week' → now - 7 days (604800 seconds).
        """
        start = _period_start("week")
        now = datetime.now()
        assert abs((now - start).total_seconds() - 604800) < 1

    def test_invalid_period(self):
        """
        Invalid period → raises ValueError (not silent return).

        Why test this? So callers know they must handle the error.
        Silent return of wrong date would be a hidden bug.
        """
        with pytest.raises(ValueError):
            _period_start("invalid")