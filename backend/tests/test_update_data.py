"""
Unit tests for backend/data/update_data.py.

All external collaborators (ARSO fetch, parsers, merge, caches and DB insert)
are replaced with fakes, so these tests cover only the control flow of
update_data(): what it calls, in what order, and what it returns.
"""
import os
from datetime import datetime

import pytest

# backend.database.session (imported through insert_data) needs DB_PASSWORD.
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")

import backend.data.update_data as update_data_module
from backend.parsers.models.measurement_model import ParsedMeasurementModel
from backend.parsers.models.parse_result import ParseResult
from backend.parsers.models.station_models import ParsedStationModel


def make_station(station_id="E403", station_name="Ljubljana Bežigrad"):
    return ParsedStationModel(
        station_id=station_id,
        station_name=station_name,
        latitude=46.0658,
        longitude=14.5125,
        d96_easting=462500.0,
        d96_northing=101500.0,
        elevation_meters=298,
    )


def make_measurement(**overrides):
    defaults = dict(
        station_id="E403",
        station_name="Ljubljana Bežigrad",
        time_from=datetime(2026, 1, 1, 10, 0),
        time_to=datetime(2026, 1, 1, 11, 0),
        pm10=21,
    )
    defaults.update(overrides)
    return ParsedMeasurementModel(**defaults)


class Calls:
    """Collects what update_data() invoked."""

    def __init__(self):
        self.cached = []
        self.inserted = []
        self.refreshed = 0

    def cache(self, merged_data):
        self.cached.append(merged_data)

    def insert(self, all_parsed_data):
        self.inserted.append(all_parsed_data)
        return self.insert_return

    def refresh(self):
        self.refreshed += 1
        return self.refresh_return


@pytest.fixture
def calls(monkeypatch):
    calls = Calls()
    calls.insert_return = True
    calls.refresh_return = True

    def fake_insert(all_parsed_data):
        return calls.insert(all_parsed_data)

    def fake_refresh():
        return calls.refresh()

    monkeypatch.setattr(update_data_module, "insert_merged_data_into_cache", calls.cache)
    monkeypatch.setattr(update_data_module, "insert_all_data", fake_insert)
    monkeypatch.setattr(update_data_module, "refresh_history_cache", fake_refresh)
    monkeypatch.delenv("SKIP_DB_SYNC", raising=False)
    return calls


def patch_pipeline(monkeypatch, stations, measurements, merged_data):
    monkeypatch.setattr(
        update_data_module,
        "fetch_arso_xml",
        lambda: (True, "<xml/>", None),
    )
    monkeypatch.setattr(
        update_data_module,
        "parse_stations_from_xml",
        lambda xml: ParseResult(success=True, data=stations, items_parsed=len(stations)),
    )
    monkeypatch.setattr(
        update_data_module,
        "parse_measurements_from_xml",
        lambda xml: ParseResult(
            success=True, data=measurements, items_parsed=len(measurements)
        ),
    )
    monkeypatch.setattr(
        update_data_module,
        "merge_stations_and_measurements",
        lambda s, m: merged_data,
    )


def test_update_data_inserts_then_refreshes(monkeypatch, calls):
    station = make_station()
    m1 = make_measurement(pm10=21)
    m2 = make_measurement(
        time_from=datetime(2026, 1, 1, 11, 0),
        time_to=datetime(2026, 1, 1, 12, 0),
        pm10=30,
    )
    merged = {"E403": {"info": station, "measurements_list": [m1, m2]}}
    patch_pipeline(monkeypatch, [station], [m1, m2], merged)

    assert update_data_module.update_data() is True
    assert calls.cached == [merged]
    assert calls.inserted == [[(station, m1), (station, m2)]]
    assert calls.refreshed == 1


def test_update_data_skips_history_refresh_when_insert_fails(monkeypatch, calls):
    calls.insert_return = False
    station = make_station()
    measurement = make_measurement()
    merged = {"E403": {"info": station, "measurements_list": [measurement]}}
    patch_pipeline(monkeypatch, [station], [measurement], merged)

    assert update_data_module.update_data() is False
    # Merged data is still cached (that happens before the DB insert)...
    assert len(calls.cached) == 1
    # ...but the history cache must not be rebuilt from a failed insert.
    assert calls.inserted == [[(station, measurement)]]
    assert calls.refreshed == 0


def test_update_data_with_skip_db_sync_skips_insert_and_refresh(monkeypatch, calls):
    monkeypatch.setenv("SKIP_DB_SYNC", "1")
    station = make_station()
    measurement = make_measurement()
    merged = {"E403": {"info": station, "measurements_list": [measurement]}}
    patch_pipeline(monkeypatch, [station], [measurement], merged)

    assert update_data_module.update_data() is True
    assert len(calls.cached) == 1
    assert calls.inserted == []
    assert calls.refreshed == 0


def test_update_data_returns_false_when_fetch_fails(monkeypatch, calls):
    monkeypatch.setattr(
        update_data_module, "fetch_arso_xml", lambda: (False, None, "timeout")
    )

    assert update_data_module.update_data() is False
    assert calls.cached == []
    assert calls.inserted == []
    assert calls.refreshed == 0


def test_update_data_returns_false_when_station_parse_fails(monkeypatch, calls):
    monkeypatch.setattr(
        update_data_module, "fetch_arso_xml", lambda: (True, "<xml/>", None)
    )
    monkeypatch.setattr(
        update_data_module,
        "parse_stations_from_xml",
        lambda xml: ParseResult(
            success=False, data=[], items_parsed=0, error_message="bad xml"
        ),
    )

    assert update_data_module.update_data() is False
    assert calls.cached == []
    assert calls.inserted == []


def test_update_data_returns_false_when_measurement_parse_fails(monkeypatch, calls):
    monkeypatch.setattr(
        update_data_module, "fetch_arso_xml", lambda: (True, "<xml/>", None)
    )
    monkeypatch.setattr(
        update_data_module,
        "parse_stations_from_xml",
        lambda xml: ParseResult(success=True, data=[make_station()], items_parsed=1),
    )
    monkeypatch.setattr(
        update_data_module,
        "parse_measurements_from_xml",
        lambda xml: ParseResult(
            success=False, data=[], items_parsed=0, error_message="bad xml"
        ),
    )

    assert update_data_module.update_data() is False
    assert calls.cached == []
    assert calls.inserted == []


def test_update_data_returns_false_when_merge_is_empty(monkeypatch, calls):
    patch_pipeline(monkeypatch, [], [], {})

    assert update_data_module.update_data() is False
    assert calls.cached == []
    assert calls.inserted == []
