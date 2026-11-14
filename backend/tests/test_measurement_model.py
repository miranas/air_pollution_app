"""
Tests for ParsedMeasurementModel.from_xml_element / validation.

Covers the ARSO value quirks: values below the detection limit ("<2"),
missing values, and invalid timestamps.
"""
from datetime import datetime
from xml.etree import ElementTree as ET

import pytest

from backend.parsers.models.measurement_model import ParsedMeasurementModel


def parse(xml):
    return ParsedMeasurementModel.from_xml_element(ET.fromstring(xml))


def test_parses_all_pollutants():
    measurement = parse(
        """
        <postaja sifra="E403">
            <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
            <datum_od>2026-01-01 10:00</datum_od>
            <datum_do>2026-01-01 11:00</datum_do>
            <co>0.4</co>
            <o3>55</o3>
            <no2>12</no2>
            <so2>3</so2>
            <pm10>21</pm10>
            <pm2.5>8</pm2.5>
            <benzen>1.2</benzen>
            <nox>20</nox>
        </postaja>
        """
    )

    assert measurement.station_id == "E403"
    assert measurement.station_name == "Ljubljana Bežigrad"
    assert measurement.time_from == datetime(2026, 1, 1, 10, 0)
    assert measurement.time_to == datetime(2026, 1, 1, 11, 0)
    assert measurement.co == 0.4
    assert measurement.o3 == 55
    assert measurement.no2 == 12
    assert measurement.so2 == 3
    assert measurement.pm10 == 21
    assert measurement.pm25 == 8
    assert measurement.benzen == 1.2
    assert measurement.nox == 20


def test_integer_pollutants_below_detection_limit_use_the_bound():
    measurement = parse(
        """
        <postaja sifra="E403">
            <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
            <datum_od>2026-01-01 10:00</datum_od>
            <datum_do>2026-01-01 11:00</datum_do>
            <pm10>&lt;2</pm10>
        </postaja>
        """
    )

    assert measurement.pm10 == 2


def test_float_pollutants_below_detection_limit_use_the_bound():
    """Regression: "<0.5" used to become "<" and silently parse as None."""
    measurement = parse(
        """
        <postaja sifra="E403">
            <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
            <datum_od>2026-01-01 10:00</datum_od>
            <datum_do>2026-01-01 11:00</datum_do>
            <co>&lt;0.5</co>
            <benzen>&lt;0.1</benzen>
        </postaja>
        """
    )

    assert measurement.co == 0.5
    assert measurement.benzen == 0.1


def test_missing_and_invalid_values_become_none():
    measurement = parse(
        """
        <postaja sifra="E403">
            <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
            <datum_od>2026-01-01 10:00</datum_od>
            <datum_do>2026-01-01 11:00</datum_do>
            <pm10></pm10>
            <o3>n/a</o3>
        </postaja>
        """
    )

    assert measurement.pm10 is None
    assert measurement.o3 is None
    assert measurement.no2 is None


def test_missing_time_range_raises():
    with pytest.raises(ValueError, match="Missing time_from or time_to"):
        parse(
            """
            <postaja sifra="E403">
                <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
                <datum_od>2026-01-01 10:00</datum_od>
            </postaja>
            """
        )


def test_invalid_time_range_raises():
    with pytest.raises(ValueError, match="Time range is invalid"):
        parse(
            """
            <postaja sifra="E403">
                <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
                <datum_od>2026-01-01 11:00</datum_od>
                <datum_do>2026-01-01 10:00</datum_do>
            </postaja>
            """
        )


def test_missing_station_id_raises():
    with pytest.raises(ValueError, match="Invalid station ID"):
        parse(
            """
            <postaja>
                <merilno_mesto>Ljubljana Bežigrad</merilno_mesto>
                <datum_od>2026-01-01 10:00</datum_od>
                <datum_do>2026-01-01 11:00</datum_do>
            </postaja>
            """
        )
