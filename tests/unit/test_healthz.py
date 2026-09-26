from fastapi.testclient import TestClient

from homebrain.config import load_settings
from homebrain.http.app import create_app


def test_healthz():
    client = TestClient(create_app(load_settings({})))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_hidden_outside_local():
    client = TestClient(create_app(load_settings({"HB_ENV": "aws"})))
    assert client.get("/docs").status_code == 404
