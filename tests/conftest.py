import os

# Prevent scheduler and update_data() in tests.
# Without this, every test would fetch ARSO XML and insert into
# the production database. This variable is not set in production,
# so behavior there is unchanged.
# os.environmet
# os.environment ["AIR_POLLUTION_SKIP_STARTUP"] = "1" should stay before from backend.app import app as flask_app

os.environ["AIR_POLLUTION_SKIP_STARTUP"] = "1"

import pytest
from backend.app import app as flask_app


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
