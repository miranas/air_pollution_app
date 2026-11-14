"""
Insert parsed ARSO data into the database.

Takes ParsedMeasurementModel and ParsedStationModel objects from the parser
and inserts them into the database using SQLAlchemy.

Functions:
    ensure_pollutants_in_db        - add missing pollutants (pm25, no2, ...)
    get_or_create_station           - find station or insert if missing
    insert_measurements_for_station - insert measurements for one station
    insert_data_into_db             - orchestrate above for one (station, measurement)
    insert_all_data                 - orchestrate all tuples + commit + bool

Transaction strategy:
    - One commit per insert_all_data call (no intermediate commits).
    - Each (station, measurement) tuple is inserted inside a SAVEPOINT, so one
      bad tuple is rolled back alone instead of discarding the whole batch.
    - If every tuple fails, the whole transaction is rolled back.
    - Returns True/False so update_data knows whether to refresh history cache.
"""
import logging
from typing import List, Optional, Tuple

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.database.db_models import (
    DbModelMeasurement,
    DbModelPollutant,
    DbModelStation,
)
from backend.database.session import SessionLocal
from backend.parsers.models.measurement_model import ParsedMeasurementModel
from backend.parsers.models.station_models import ParsedStationModel


def ensure_pollutants_in_db(db: Session) -> None:
    """
    Ensure all pollutants referenced in ParsedMeasurementModel exist in DB.

    Reads existing pollutant names, inserts any missing ones with default unit
    (mg/m³ for CO, μg/m³ for others).

    Does NOT commit: the caller commits the whole batch as one transaction, so
    a later rollback also removes these rows.

    Args:
        db: SQLAlchemy session.
    """
    existing = {p.name for p in db.query(DbModelPollutant).all()}
    metadata = {"station_id", "station_name", "time_from", "time_to"}
    pollutant_fields = [
        f for f in ParsedMeasurementModel.__dataclass_fields__.keys()
        if f not in metadata
    ]

    for field in pollutant_fields:
        if field in existing:
            continue
        stmt = insert(DbModelPollutant).values(
            name=field,
            unit="mg/m³" if field == "co" else "μg/m³",
        ).on_conflict_do_nothing(index_elements=['name'])
        db.execute(stmt)


def get_or_create_station(
    db: Session,
    parsed_station: ParsedStationModel,
) -> DbModelStation:
    """
    Get existing station or create a new one.

    Args:
        db: SQLAlchemy session.
        parsed_station: ParsedStationModel with station attributes.

    Returns:
        DbModelStation: ORM instance (existing or newly created).

    Raises:
        ValueError: If station cannot be found after insert.
    """
    station = db.query(DbModelStation).filter_by(
        station_id=parsed_station.station_id
    ).first()
    if station:
        return station

    stmt = insert(DbModelStation).values(
        station_id=parsed_station.station_id,
        station_name=parsed_station.station_name,
        latitude=parsed_station.latitude,
        longitude=parsed_station.longitude,
        d96_easting=parsed_station.d96_easting,
        d96_northing=parsed_station.d96_northing,
        elevation_meters=parsed_station.elevation_meters,
    ).on_conflict_do_nothing(index_elements=['station_id'])
    db.execute(stmt)
    db.flush()

    # Re-query: insert() returns Insert object, not ORM instance.
    # We need the instance to get .id for measurements.
    station = db.query(DbModelStation).filter_by(
        station_id=parsed_station.station_id
    ).first()
    if station is None:
        raise ValueError(
            f"Station {parsed_station.station_id} not found after insert"
        )
    return station


def insert_measurements_for_station(
    db: Session,
    station: DbModelStation,
    parsed_measurements: ParsedMeasurementModel,
    pollutants: Optional[List[DbModelPollutant]] = None,
) -> None:
    """
    Insert measurements for one station and one time point.

    Args:
        db: SQLAlchemy session.
        station: DbModelStation instance (has .id).
        parsed_measurements: ParsedMeasurementModel with pollutant values.
        pollutants: Optional preloaded pollutant rows. Pass this from batch
            callers to avoid re-querying the pollutants table for every tuple.
    """
    measurement_time = getattr(parsed_measurements, "time_to", None)

    if pollutants is None:
        pollutants = db.query(DbModelPollutant).all()

    for pollutant in pollutants:
        value = getattr(parsed_measurements, pollutant.name, None)
        if value is None:
            continue

        stmt = insert(DbModelMeasurement).values(
            station_id=station.id,
            pollutant_id=pollutant.id,
            value=value,
            measured_at=measurement_time,
        ).on_conflict_do_nothing(
            index_elements=['station_id', 'pollutant_id', 'measured_at']
        )
        db.execute(stmt)


def insert_data_into_db(
    db: Session,
    parsed_station: ParsedStationModel,
    parsed_measurements: ParsedMeasurementModel,
    pollutants: Optional[List[DbModelPollutant]] = None,
) -> None:
    """
    Insert one station (if missing) and its measurements.

    Does NOT commit - caller (insert_all_data) commits at the end.
    On error, exception propagates to caller.

    Args:
        db: SQLAlchemy session.
        parsed_station: ParsedStationModel with station attributes.
        parsed_measurements: ParsedMeasurementModel with pollutant values.
        pollutants: Optional preloaded pollutant rows (see
            insert_measurements_for_station).
    """
    station = get_or_create_station(db, parsed_station)
    insert_measurements_for_station(
        db, station, parsed_measurements, pollutants
    )


def insert_all_data(
    all_parsed_data: List[Tuple[ParsedStationModel, ParsedMeasurementModel]]
) -> bool:
    """
    Insert stations and measurements for one hourly update.

    Single transaction for the whole batch. Each tuple runs in its own
    SAVEPOINT: a failing tuple is rolled back alone and the rest of the batch
    is still committed. If every tuple fails, the whole transaction is rolled
    back.

    Args:
        all_parsed_data: List of (ParsedStationModel, ParsedMeasurementModel) tuples.

    Returns:
        bool: True if the batch was committed (possibly with skipped tuples),
            False if the insert failed entirely.
            On failure, caller (update_data) should skip history refresh.
    """
    db = SessionLocal()
    try:
        ensure_pollutants_in_db(db)

        # Load pollutants once per batch instead of once per tuple (N+1).
        pollutants = db.query(DbModelPollutant).all()

        failed = 0
        for parsed_station, parsed_measurements in all_parsed_data:
            try:
                with db.begin_nested():
                    insert_data_into_db(
                        db, parsed_station, parsed_measurements, pollutants
                    )
            except Exception:
                failed += 1
                logging.exception(
                    "Skipping tuple for station %s: insert failed",
                    parsed_station.station_id,
                )

        if all_parsed_data and failed == len(all_parsed_data):
            logging.error(
                "All %d tuples failed - rolling back",
                len(all_parsed_data),
            )
            db.rollback()
            return False

        db.commit()

        if failed:
            logging.warning(
                "Inserted %d/%d tuples, skipped %d",
                len(all_parsed_data) - failed,
                len(all_parsed_data),
                failed,
            )
        return True
    except Exception:
        db.rollback()
        logging.exception(
            "Database insert failed for %d tuples - rolled back",
            len(all_parsed_data),
        )
        return False
    finally:
        db.close()