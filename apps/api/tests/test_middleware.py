"""MaxBodySizeMiddleware: reject an oversized request body before it reaches a route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_oversized_body_is_rejected_with_413() -> None:
    huge_filename = "a" * (2 * 1024 * 1024)
    response = client.post(
        "/uploads",
        json={"filename": huge_filename, "size": 1},
        headers={"Authorization": "Bearer ignored"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_normal_sized_body_is_not_rejected_by_the_middleware() -> None:
    # No auth override here — this only proves the middleware lets a small request
    # through to the route (which then 401s for lack of a real token), not 413.
    response = client.post("/uploads", json={"filename": "model.onnx", "size": 1})
    assert response.status_code != 413
