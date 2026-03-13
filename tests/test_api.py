from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job_dry_run(repo_root: Path) -> None:
    client = TestClient(app)
    response = client.post(
        "/jobs",
        json={
            "job": "为服务增加 /healthz endpoint 并输出交付包",
            "mode": "dry-run",
            "repo_path": str(repo_root),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_human"
    assert Path(payload["artifacts"]["delivery"]).exists()
