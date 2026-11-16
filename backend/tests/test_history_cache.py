"""
Unit tests for the pure history-payload transform.

These tests cover `_build_history_payload` only: it takes DB rows and returns
the API payload, without touching the database, Redis or Flask. The sync and
async builders both delegate to it, so this is the contract both must keep.
"""
import os
from datetime import datetime
from types import SimpleNamespace

# backend.database.session (imported through history_cache) needs DB_PASSWORD.
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")

from backend.utils.history_cache import _build_history_payload


def make_station(
    station_id="E403",
    station_name="Ljubljana Bežigrad",
    latitude=46.0658,
    longitude=14.5125,
):
    return SimpleNamespace(
        id=1,
        station_id=station_id,
        station_name=station_name,
        latitude=latitude,
        longitude=longitude,
    )


def make_row(measured_at, value, pollutant_name="pm10", station=None):
    station = station or make_station()
    measurement = SimpleNamespace(measured_at=measured_at, value=value)
    pollutant = SimpleNamespace(name=pollutant_name)
    return (station, measurement, pollutant)


def test_build_history_payload_with_no_rows():
    start = datetime(2026, 1, 1, 0, 0)
    end = datetime(2026, 1, 2, 0, 0)

    payload = _build_history_payload([], "day", start, end)

    assert payload["period"] == "day"
    assert payload["from"] == "2026-01-01T00:00:00"
    assert payload["to"] == "2026-01-02T00:00:00"
    assert payload["stations"] == {}


def test_build_history_payload_groups_pollutants_per_time():
    start = datetime(2026, 1, 1, 10, 0)
    end = datetime(2026, 1, 1, 11, 0)
    measured_at = datetime(2026, 1, 1, 10, 30)

    rows = [
        make_row(measured_at, 21.5, "pm10"),
        make_row(measured_at, 14.0, "no2"),
        make_row(measured_at, 3.2, "co"),
    ]

    payload = _build_history_payload(rows, "day", start, end)

    station = payload["stations"]["E403"]
    assert station["info"]["station_name"] == "Ljubljana Bežigrad"
    assert station["total_points"] == 1

    # One time bucket, all pollutants on the same measurement dict.
    # Aggregation rewrites time_to to the bucket boundary (end of the hour).
    assert len(station["measurements_list"]) == 1
    measurement = station["measurements_list"][0]
    assert measurement["time_to"] == "2026-01-01T11:00:00"
    assert measurement["pm10"] == 21.5
    assert measurement["no2"] == 14.0
    assert measurement["co"] == 3.2


def test_build_history_payload_aggregates_within_one_hour_bucket():
    start = datetime(2026, 1, 1, 10, 0)
    end = datetime(2026, 1, 1, 11, 0)
    rows = [
        make_row(datetime(2026, 1, 1, 10, 15), 10.0),
        make_row(datetime(2026, 1, 1, 10, 45), 20.0),
    ]

    payload = _build_history_payload(rows, "day", start, end)

    station = payload["stations"]["E403"]
    # Two raw points were bucketed into a single 1h average.
    assert station["total_points"] == 2
    assert len(station["measurements_list"]) == 1
    assert station["measurements_list"][0]["pm10"] == 15.0


def test_build_history_payload_keeps_multiple_stations_and_sorts_newest_first():
    start = datetime(2026, 1, 1, 10, 0)
    end = datetime(2026, 1, 1, 13, 0)
    older = datetime(2026, 1, 1, 10, 15)
    newer = datetime(2026, 1, 1, 12, 15)
    ljubljana = make_station("E403", "Ljubljana Bežigrad")
    maribor = make_station("E101", "Maribor Center")

    rows = [
        make_row(older, 10.0, "pm10", station=ljubljana),
        make_row(newer, 30.0, "pm10", station=ljubljana),
        make_row(newer, 5.0, "pm10", station=maribor),
    ]

    payload = _build_history_payload(rows, "day", start, end)

    assert set(payload["stations"]) == {"E403", "E101"}
    ljubljana_points = payload["stations"]["E403"]["measurements_list"]
    assert len(ljubljana_points) == 2
    # Newest first, as the API expects.
    assert ljubljana_points[0]["time_to"] > ljubljana_points[1]["time_to"]
    assert ljubljana_points[0]["pm10"] == 30.0
