import pytest
from cot_proxy import app as flask_app
import os
from unittest.mock import patch

@pytest.fixture(scope='module')
def app():
    """Instance of Flask application."""
    # You might want to set app.config['TESTING'] = True
    # and other test-specific configurations here.
    # For example, if your app uses a database, you might set up a test database.
    flask_app.config.update({
        "TESTING": True,
        # Add any other specific test configurations here
        # e.g., "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"
    })

    # Other setup can go here

    yield flask_app

    # Clean up / reset resources here if necessary
    # For example, dropping test database tables

@pytest.fixture(scope='module')
def client(app):
    """A test client for the app."""
    return app.test_client()
  
@pytest.fixture
def enable_debug(mocker):
    """Enable DEBUG logging for the duration of the test."""
    # Patch the DEBUG environment variable
    mocker.patch.dict(os.environ, {"DEBUG": "true"}, clear=True)
    # Optionally patch the module-level logger setup if needed
    # (Not required if tests already use `caplog` and `DEBUG` is set globally)
    yield

# You can add other shared fixtures here, for example,
# a fixture to mock os.getenv if it's used extensively
# across multiple test files.
#
# import os
# from unittest.mock import patch
#
# @pytest.fixture
# def mock_env_vars(monkeypatch):
#     """Fixture to mock environment variables."""
#     env_vars = {}
#     def set_env(name, value):
#         env_vars[name] = value
#         monkeypatch.setenv(name, value)
#
#     def get_env(name, default=None):
#         return env_vars.get(name, default)
#
#     with patch.dict(os.environ, env_vars, clear=True):
#         yield set_env, get_env