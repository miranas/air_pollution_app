"""
Unit tests for backend/parsers/insert_data.py.

The module is tested without a real PostgreSQL connection: SessionLocal is
replaced by FakeSession, which records SQL statements and emulates just enough
of a session (query / execute / flush / commit / rollback / close) for the
orchestration logic under test.

Insert statements are PostgreSQL-specific (ON CONFLICT DO NOTHING), so they
are inspected by compiling them with the PostgreSQL dialect - exactly what the
real engine would do - instead of executing them against SQLite.
"""
import os
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

# backend.database.session reads these at import time and raises without
# DB_PASSWORD. Tests never connect, so dummy values are enough.
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")

from sqlalchemy.dialects.postgresql import dialect as pg_dialect

import backend.parsers.insert_data as insert_data_module
from backend.database.db_models import (
    DbModelMeasurement,
    DbModelPollutant,
    DbModelStation,
)
from backend.parsers.models.measurement_model import ParsedMeasurementModel
from backend.parsers.models.station_models import ParsedStationModel


# ---------------------------------------------------------------------------
# Fake SQLAlchemy session
# ---------------------------------------------------------------------------
class FakeQuery:
    """Minimal stand-in for Session.query(Model)."""

    def __init__(self, session, model, filters=None):
        self._session = session
        self._model = model
        self._filters = filters or {}

    def filter_by(self, **kwargs):
        return FakeQuery(
            self._session, self._model, {**self._filters, **kwargs}
        )

    def all(self):
        return list(self._session.rows_for(self._model))

    def first(self):
        for row in self._session.rows_for(self._model):
            if all(
                getattr(row, key) == value
                for key, value in self._filters.items()
            ):
                return row
        return None


class FakeSession:
    """Records statements instead of talking to a database."""

    def __init__(
        self,
        pollutants=(),
        stations=(),
        fail_on_execute=False,
        record_inserted_stations=True,
    ):
        self.pollutants = list(pollutants)
        self.stations = list(stations)
        self.executed = []
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.savepoints = 0
        self.savepoint_rollbacks = 0
        self.closed = False
        self.fail_on_execute = fail_on_execute
        self.record_inserted_stations = record_inserted_stations
        self._next_pk = 1000

    # -- Session API used by insert_data --------------------------------
    def query(self, model):
        self.queries.append(model.__name__)
        return FakeQuery(self, model)

    @contextmanager
    def begin_nested(self):
        self.savepoints += 1
        try:
            yield self
        except Exception:
            self.savepoint_rollbacks += 1
            raise

    def execute(self, stmt):
        if self.fail_on_execute:
            raise RuntimeError("simulated database failure")

        self.executed.append(stmt)
        params = compiled_params(stmt)
        table = stmt.table.name

        if table == "pollutants":
            self.pollutants.append(
                SimpleNamespace(id=self._new_pk(), **params)
            )
        elif table == "stations" and self.record_inserted_stations:
            self.stations.append(
                SimpleNamespace(id=self._new_pk(), **params)
            )

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    # -- helpers --------------------------------------------------------
    def _new_pk(self):
        self._next_pk += 1
        return self._next_pk

    def rows_for(self, model):
        if model is DbModelPollutant:
            return self.pollutants
        if model is DbModelStation:
            return self.stations
        return []


def compiled_params(stmt):
    return stmt.compile(dialect=pg_dialect()).params


def statements_for(session, table_name):
    return [stmt for stmt in session.executed if stmt.table.name == table_name]


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
        co=None,
        o3=None,
        no2=None,
        so2=None,
        pm10=None,
        pm25=None,
        nox=None,
        benzen=None,
    )
    defaults.update(overrides)
    return ParsedMeasurementModel(**defaults)


@pytest.fixture
def use_session(monkeypatch):
    """Make insert_all_data use the given FakeSession."""

    def _use(session):
        monkeypatch.setattr(insert_data_module, "SessionLocal", lambda: session)
        return session

    return _use


# ---------------------------------------------------------------------------
# ensure_pollutants_in_db
# ---------------------------------------------------------------------------
def test_ensure_pollutants_inserts_all_dataclass_fields():
    session = FakeSession()

    insert_data_module.ensure_pollutants_in_db(session)

    inserted = {
        compiled_params(stmt)["name"] for stmt in statements_for(session, "pollutants")
    }
    assert inserted == {"co", "o3", "no2", "so2", "pm10", "pm25", "nox", "benzen"}
    # No commit here: the batch caller owns the transaction.
    assert session.commits == 0


def test_ensure_pollutants_uses_correct_units():
    session = FakeSession()

    insert_data_module.ensure_pollutants_in_db(session)

    units = {
        compiled_params(stmt)["name"]: compiled_params(stmt)["unit"]
        for stmt in statements_for(session, "pollutants")
    }
    assert units["co"] == "mg/m³"
    assert all(
        unit == "μg/m³" for name, unit in units.items() if name != "co"
    )


def test_ensure_pollutants_skips_existing_names():
    session = FakeSession(
        pollutants=[SimpleNamespace(id=1, name="pm10", unit="μg/m³")]
    )

    insert_data_module.ensure_pollutants_in_db(session)

    names = [
        compiled_params(stmt)["name"]
        for stmt in statements_for(session, "pollutants")
    ]
    assert "pm10" not in names
    assert len(names) == 7


def test_insert_statements_are_postgres_on_conflict_statements():
    """Regression guard: generic sqlalchemy.insert has no on_conflict_do_nothing."""
    session = FakeSession()

    insert_data_module.ensure_pollutants_in_db(session)

    stmt = statements_for(session, "pollutants")[0]
    sql = str(stmt.compile(dialect=pg_dialect()))
    assert "ON CONFLICT (name) DO NOTHING" in sql


# ---------------------------------------------------------------------------
# get_or_create_station
# ---------------------------------------------------------------------------
def test_get_or_create_station_returns_existing_without_insert():
    existing = SimpleNamespace(id=7, station_id="E403")
    session = FakeSession(stations=[existing])

    station = insert_data_module.get_or_create_station(session, make_station())

    assert station is existing
    assert statements_for(session, "stations") == []


def test_get_or_create_station_inserts_and_requeries():
    session = FakeSession()

    station = insert_data_module.get_or_create_station(session, make_station())

    inserts = statements_for(session, "stations")
    assert len(inserts) == 1
    params = compiled_params(inserts[0])
    assert params["station_id"] == "E403"
    assert params["station_name"] == "Ljubljana Bežigrad"
    assert params["elevation_meters"] == 298
    # The returned object is reloaded from the session (has the DB primary key)
    assert station.station_id == "E403"
    assert station.id == session.stations[0].id
    assert session.flushes == 1


def test_get_or_create_station_raises_when_still_missing_after_insert():
    session = FakeSession(record_inserted_stations=False)

    with pytest.raises(ValueError, match="not found after insert"):
        insert_data_module.get_or_create_station(session, make_station())

    assert session.flushes == 1


# ---------------------------------------------------------------------------
# insert_measurements_for_station
# ---------------------------------------------------------------------------
def test_insert_measurements_skips_missing_and_keeps_zero_values():
    pollutants = [
        SimpleNamespace(id=1, name="pm10"),
        SimpleNamespace(id=2, name="no2"),
        SimpleNamespace(id=3, name="co"),
    ]
    station = SimpleNamespace(id=42, station_id="E403")
    measurement = make_measurement(pm10=0, no2=None, co=0.4)
    session = FakeSession(pollutants=pollutants)

    insert_data_module.insert_measurements_for_station(
        session, station, measurement
    )

    rows = [compiled_params(s) for s in statements_for(session, "measurements")]
    by_pollutant = {row["pollutant_id"]: row for row in rows}
    assert set(by_pollutant) == {1, 3}  # no2 (None) skipped, pm10=0 kept
    assert by_pollutant[1]["value"] == 0
    assert by_pollutant[3]["value"] == 0.4


def test_insert_measurements_uses_station_pk_and_time_to():
    station = SimpleNamespace(id=42, station_id="E403")
    measurement = make_measurement(pm25=17)
    session = FakeSession(pollutants=[SimpleNamespace(id=5, name="pm25")])

    insert_data_module.insert_measurements_for_station(
        session, station, measurement
    )

    row = compiled_params(statements_for(session, "measurements")[0])
    assert row["station_id"] == 42  # FK to stations.id, not the ARSO code
    assert row["pollutant_id"] == 5
    assert row["value"] == 17
    assert row["measured_at"] == measurement.time_to


def test_insert_data_into_db_does_not_commit():
    session = FakeSession(pollutants=[SimpleNamespace(id=1, name="pm10")])

    insert_data_module.insert_data_into_db(
        session, make_station(), make_measurement(pm10=12)
    )

    assert session.commits == 0
    assert len(statements_for(session, "stations")) == 1
    assert len(statements_for(session, "measurements")) == 1


# ---------------------------------------------------------------------------
# insert_all_data
# ---------------------------------------------------------------------------
def test_insert_all_data_success_commits_and_closes(use_session):
    session = use_session(FakeSession())
    data = [(make_station(), make_measurement(pm10=21, o3=55))]

    result = insert_data_module.insert_all_data(data)

    assert result is True
    assert session.closed is True
    assert session.rollbacks == 0
    assert session.commits == 1  # exactly one commit for the whole batch
    assert len(statements_for(session, "measurements")) == 2


def test_insert_all_data_with_no_tuples_still_succeeds(use_session):
    session = use_session(FakeSession())

    result = insert_data_module.insert_all_data([])

    assert result is True
    assert session.commits == 1
    assert session.closed is True


def test_insert_all_data_rolls_back_and_returns_false_on_error(use_session):
    session = use_session(FakeSession(fail_on_execute=True))

    result = insert_data_module.insert_all_data(
        [(make_station(), make_measurement(pm10=21))]
    )

    assert result is False
    assert session.rollbacks == 1
    assert session.commits == 0
    assert session.closed is True


def test_insert_all_data_logs_exception(use_session, caplog):
    use_session(FakeSession(fail_on_execute=True))

    with caplog.at_level("ERROR"):
        insert_data_module.insert_all_data(
            [(make_station(), make_measurement(pm10=21))]
        )

    assert "Database insert failed" in caplog.text


def test_insert_all_data_handles_multiple_stations_and_timepoints(use_session):
    session = use_session(FakeSession())
    data = [
        (make_station("E403"), make_measurement(station_id="E403", pm10=10)),
        (
            make_station("E401", "Ljubljana Center"),
            make_measurement(
                station_id="E401",
                station_name="Ljubljana Center",
                pm10=20,
            ),
        ),
        (
            make_station("E403"),
            make_measurement(
                station_id="E403",
                time_from=datetime(2026, 1, 1, 11, 0),
                time_to=datetime(2026, 1, 1, 12, 0),
                pm10=30,
            ),
        ),
    ]

    result = insert_data_module.insert_all_data(data)

    assert result is True
    station_rows = [compiled_params(s) for s in statements_for(session, "stations")]
    # Station E403 is reported twice but must be inserted only once.
    assert [row["station_id"] for row in station_rows] == ["E403", "E401"]
    measurement_rows = [
        compiled_params(s) for s in statements_for(session, "measurements")
    ]
    assert sorted(row["value"] for row in measurement_rows) == [10, 20, 30]
    # Two fixed pollutant queries per batch (one in ensure_pollutants_in_db,
    # one to load rows for the inserts) - not one per tuple (N+1).
    assert session.queries.count("DbModelPollutant") == 2


def test_insert_all_data_skips_only_failing_tuple(use_session, monkeypatch):
    session = use_session(FakeSession())
    real_insert = insert_data_module.insert_data_into_db

    def insert_one_by_one(db, station, measurement, pollutants=None):
        if station.station_id == "E401":
            raise RuntimeError("simulated bad tuple")
        return real_insert(db, station, measurement, pollutants)

    monkeypatch.setattr(
        insert_data_module, "insert_data_into_db", insert_one_by_one
    )
    data = [
        (make_station("E403"), make_measurement(station_id="E403", pm10=10)),
        (
            make_station("E401", "Ljubljana Center"),
            make_measurement(
                station_id="E401",
                station_name="Ljubljana Center",
                pm10=20,
            ),
        ),
        (make_station("E403"), make_measurement(station_id="E403", pm10=30)),
    ]

    result = insert_data_module.insert_all_data(data)

    assert result is True
    assert session.savepoints == 3
    assert session.savepoint_rollbacks == 1
    assert session.commits == 1
    # The bad tuple was rolled back to its savepoint; the other two survived.
    station_ids = [
        compiled_params(s)["station_id"]
        for s in statements_for(session, "stations")
    ]
    assert station_ids.count("E403") == 1
    assert "E401" not in station_ids
    values = [
        compiled_params(s)["value"]
        for s in statements_for(session, "measurements")
    ]
    assert sorted(values) == [10, 30]


def test_insert_all_data_rolls_back_when_every_tuple_fails(
    use_session, monkeypatch
):
    session = use_session(FakeSession())

    def always_fail(db, station, measurement, pollutants=None):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        insert_data_module, "insert_data_into_db", always_fail
    )
    data = [
        (make_station("E403"), make_measurement(station_id="E403", pm10=10)),
        (make_station("E401"), make_measurement(station_id="E401", pm10=20)),
    ]

    result = insert_data_module.insert_all_data(data)

    assert result is False
    assert session.savepoints == 2
    assert session.savepoint_rollbacks == 2
    assert session.rollbacks == 1
    assert session.commits == 0
    assert session.closed is True
