"""
Unit tests for the history cache helpers.

Only cache mechanics are covered here: key naming, serialization, and the
"no cache available" behaviour outside a Flask application context. Payload
building is covered in ``test_history_payload.py``.
"""
import os

# backend.database.session (imported through history_payload) needs DB_PASSWORD.
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")

from backend.utils.history_cache import (
    _cache_key,
    _deserialize_payload,
    _read_cached_raw_value,
    _serialize_payload,
    _write_cached_raw_value,
)


def test_cache_key_uses_stable_prefix():
    assert _cache_key("day") == "history_payload:day"
    assert _cache_key("year") == "history_payload:year"


def test_serialize_and_deserialize_roundtrip():
    payload = {
        "period": "day",
        "stations": {"E403": {"info": {"station_name": "Ljubljana Bežigrad"}}},
    }

    raw = _serialize_payload(payload)

    assert isinstance(raw, str)
    assert _deserialize_payload(raw) == payload


def test_deserialize_accepts_bytes_from_redis():
    raw = b'{"period": "week", "stations": {}}'

    assert _deserialize_payload(raw) == {"period": "week", "stations": {}}


def test_deserialize_accepts_already_decoded_dict():
    payload = {"period": "day", "stations": {}}

    assert _deserialize_payload(payload) is payload


def test_deserialize_returns_none_for_invalid_json():
    assert _deserialize_payload("{not valid json") is None
    assert _deserialize_payload(None) is None
    assert _deserialize_payload(42) is None


def test_cache_is_a_noop_outside_flask_app_context():
    # No Flask app context -> no Redis and no Flask-Caching client.
    assert _read_cached_raw_value("history_payload:day") is None
    assert _write_cached_raw_value("history_payload:day", "{}") is False
