from fastapi.testclient import TestClient
from modelforge_catalog.export import build_catalog

from app.main import app

client = TestClient(app)


def test_get_catalog_matches_build_catalog() -> None:
    response = client.get("/catalog")
    assert response.status_code == 200
    assert response.json() == build_catalog()


def test_get_catalog_requires_no_auth() -> None:
    response = client.get("/catalog", headers={})
    assert response.status_code == 200
