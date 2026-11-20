from backend.network.arso_client import fetch_arso_xml
from backend.parsers.station_parser import parse_stations_from_xml
from backend.parsers.measurments_parser import parse_measurements_from_xml
from backend.parsers.stations_and_measurments_merger import merge_stations_and_measurements
from typing import Any, List, Tuple
import os
import logging
logging.basicConfig(level=logging.INFO)
from backend.utils.redis_client import insert_merged_data_into_cache
from backend.utils.history_cache import refresh_history_cache
from backend.parsers.insert_data import insert_all_data   


def update_data() -> bool:
    """
    Run one update cycle: fetch the ARSO XML snapshot and publish it onward.

    Steps:
        1. Download the latest ARSO XML (network/arso_client.fetch_arso_xml).
        2. Parse stations and measurements into dataclasses.
        3. Merge them per station, keyed by the ARSO station code.
        4. Publish the merged snapshot to the Redis/SimpleCache layer so the
           API serves fresh data even before/without a database write.
        5. Unless SKIP_DB_SYNC is enabled, insert one
           (station, measurement) tuple per station per time point into
           PostgreSQL, then refresh the history cache.

    SKIP_DB_SYNC (environment variable, accepted truthy values: "1", "true",
    "yes"):
        Cache-only mode, used for local development and read-only deployments.
        The snapshot from step 4 is still published, but step 5 is skipped:
        nothing is written to the database and the history cache is not
        refreshed.

    Returns:
        bool: True when the cycle completed (fetch, parse, merge and cache
            write succeeded, plus the DB insert when it is enabled).
            False when fetching, parsing, merging or the DB insert failed.
            Failures are logged with their cause; callers currently react to
            the logged exception rather than to this return value.
    """
    skip_db_sync = os.environ.get("SKIP_DB_SYNC", "0").lower() in ("1", "true", "yes")

    # Fetch XML from ARSO (always returns Tuple[bool, Optional[str], Optional[str]])
    success, xml_content, error = fetch_arso_xml()    
    
    if not success or not xml_content:
        logging.error(f"Error fetching XML: {str(error)}")
        return False

    station_result = parse_stations_from_xml(xml_content)
    if not station_result.success:
        logging.error(f"Error parsing stations: {station_result.error_message}")
        return False

    # parse measurements return Measurement
    measurement_result = parse_measurements_from_xml(xml_content)
    if not measurement_result.success:
        logging.error(f"Error parsing measurements: {measurement_result.error_message}")
        return False

    # merge stations and measurements
    merged_data = merge_stations_and_measurements(
        station_result.data,
        measurement_result.data)
    
    if not merged_data:
        logging.info("No merged data available")
        return False
    else:
        # summary log
        logging.info(f"Merged data for {len(merged_data)} stations")

    # save into Redis or SimpleCache
    insert_merged_data_into_cache(merged_data)

    # Cache-only mode: the snapshot above has already been published, so the
    # API serves fresh data. Skip the DB insert and the history refresh.
    if skip_db_sync:
        logging.info("SKIP_DB_SYNC enabled: skipping DB insert and history cache refresh")
        return True

    # Debug summary of merged data
    for station_id, station_info in merged_data.items():
        logging.debug(f"Station ID: {station_id}")
        logging.debug(f"Name: {station_info['info'].station_name}")

        measurements = station_info['measurements_list']
        logging.debug(f"Measurements ({len(station_info['measurements_list'])}):")

        MAX_SHOWN = 5
        for m in measurements[:MAX_SHOWN]:
            logging.debug(f"    {m}")
        if len(measurements) > MAX_SHOWN:
            logging.debug(f"    ...and {len(measurements) - MAX_SHOWN} more\n")
        else:
            logging.debug("")

    # Build all_parsed_data from merged_data for insertion
    all_parsed_data: List[Tuple[Any, Any]] = []

    for station_id, station_and_measurements_data in merged_data.items():
        station_data = station_and_measurements_data["info"]
        for measurement_data in station_and_measurements_data["measurements_list"]:
            all_parsed_data.append((station_data, measurement_data))

    # insert_all_data() does not raise: it rolls back and returns False.
    # If the insert failed, skip the history refresh so the cache is not
    # rebuilt from a database that is missing this cycle's data.
    if not insert_all_data(all_parsed_data):
        logging.error(
            "Database insert failed for %d tuples; skipping history cache refresh",
            len(all_parsed_data),
        )
        return False

    try:
        if refresh_history_cache():
            logging.info("Refreshed history cache for all periods")
        else:
            logging.warning("History cache refresh completed with warnings")
    except Exception as e:
        logging.exception(f"Failed to refresh history cache: {e}")

    return True


""" for development and debugging purpose only
if __name__ == "__main__":
    # run function as a script!
    update_data()
"""
