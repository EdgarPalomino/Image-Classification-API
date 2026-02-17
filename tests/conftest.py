from fastapi.testclient import TestClient

from app.main import app


def get_test_client():
    """
    Simple helper if you want to import directly elsewhere.
    """
    return TestClient(app)


import pytest


@pytest.fixture(scope="session")
def client():
    """
    Session-scope TestClient, reused across all tests.
    """
    with TestClient(app) as c:
        yield c