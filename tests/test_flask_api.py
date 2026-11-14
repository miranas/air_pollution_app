def test_status_returns_200(client):
    response = client.get("/api/status")
    assert response.status_code == 200


def test_latest_returns_200(client):
    response = client.get("/api/latest")
    assert response.status_code == 200
    data = response.get_json()
    # /api/latest returns stations directly (keyed by station_id)
    assert isinstance(data, dict)
    assert len(data) > 0
    # Check that at least one station has expected structure
    first_station = next(iter(data.values()))
    assert "info" in first_station
    assert "measurements_list" in first_station


def test_history_day_returns_200(client):
    response = client.get("/api/history?period=day")
    assert response.status_code == 200
    data = response.get_json()
    assert "stations" in data
    assert "from" in data
    assert "to" in data


def test_history_invalid_period_returns_4xx(client):
    response = client.get("/api/history?period=invalid")
    assert response.status_code in (400, 422)
