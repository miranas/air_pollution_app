import pytest # testing framework
import requests # real exception types used by the client
from unittest.mock import patch, MagicMock # used to mock network calls
from backend.network.arso_client import fetch_arso_xml
from backend.network.config import REQUEST_TIMEOUT


"""
Test successful fetching of ARSO XML data.
"With patch" block replaces the real request.get
function with mock object for the duration of the with
object. When fetch_arso_xml() calls request.get,
it actually calls mock_get which returns mock_response
"""
def test_fetch_arso_xml_success():
    fake_xml = "<xml>test</xml>"
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.text = fake_xml
        mock_response.encoding = "utf-8"
        # returns no value, simulates successfull response, no Exception needed
        mock_response.raise_for_status.return_value = None
        # makes request.get return mock response
        mock_get.return_value = mock_response

        # Short way:assert fetch_arso_xml() == (True, fake_xml, None)
        success,xml_data, error = fetch_arso_xml()
        assert success is True
        assert xml_data == fake_xml
        assert error is None
        # one attempt only, with (connect, read) timeout
        assert mock_get.call_count == 1
        assert mock_get.call_args.kwargs["timeout"] == (3.05, REQUEST_TIMEOUT)


def test_fetch_arso_html_http_error():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        # raise_for_status() raises requests.HTTPError (a RequestException).
        # No .response attached -> not retryable -> fail after one attempt.
        mock_response.raise_for_status.side_effect = requests.HTTPError("Http Error")
        mock_get.return_value = mock_response

        success, xml_data, error = fetch_arso_xml()
        assert success is False
        assert xml_data is None
        assert error is not None
        assert mock_get.call_count == 1


def test_fetch_arso_xml_timeout_retries_three_times():
    with patch("requests.get") as mock_get, patch("time.sleep") as mock_sleep:
        mock_get.side_effect = requests.Timeout("timed out")

        success, xml_data, error = fetch_arso_xml()
        assert success is False
        assert xml_data is None
        assert "timeout" in error.lower()
        assert "after 3 attempt(s)" in error
        assert mock_get.call_count == 3
        assert [c.args[0] for c in mock_sleep.call_args_list] == [1.0, 2.0]


# ---------------------------------------------------------------------------
# Retry policy tests: fake requests.get + fake sleep, no real network/time.
# ---------------------------------------------------------------------------

class FakeResponse:
    text = "<xml/>"
    encoding = "utf-8"
    status_code = 200

    def raise_for_status(self):
        pass


def http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(f"{status_code} error", response=response)


def test_fetch_retries_timeout_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.Timeout("boom")
        return FakeResponse()

    monkeypatch.setattr("backend.network.arso_client.requests.get", fake_get)
    monkeypatch.setattr("backend.network.arso_client.time.sleep", sleeps.append)

    ok, xml, err = fetch_arso_xml()

    assert ok is True
    assert xml == "<xml/>"
    assert err is None
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_fetch_retries_server_errors_then_gives_up(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        raise http_error(500)

    monkeypatch.setattr("backend.network.arso_client.requests.get", fake_get)
    monkeypatch.setattr("backend.network.arso_client.time.sleep", sleeps.append)

    ok, xml, err = fetch_arso_xml()

    assert ok is False
    assert xml is None
    assert "after 3 attempt(s)" in err
    assert "500" in err
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_fetch_does_not_retry_4xx(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        raise http_error(404)

    monkeypatch.setattr("backend.network.arso_client.requests.get", fake_get)
    monkeypatch.setattr("backend.network.arso_client.time.sleep", sleeps.append)

    ok, xml, err = fetch_arso_xml()

    assert ok is False
    assert xml is None
    assert "after 1 attempt(s)" in err
    assert calls["n"] == 1
    assert sleeps == []


def test_fetch_retries_rate_limit_429(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise http_error(429)
        return FakeResponse()

    monkeypatch.setattr("backend.network.arso_client.requests.get", fake_get)
    monkeypatch.setattr("backend.network.arso_client.time.sleep", sleeps.append)

    ok, xml, err = fetch_arso_xml()

    assert ok is True
    assert xml == "<xml/>"
    assert calls["n"] == 2
    assert sleeps == [1.0]
