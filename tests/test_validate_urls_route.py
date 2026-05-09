from fastapi.testclient import TestClient

from backend.api.main import create_app


def test_validate_urls_invalid_and_valid():
    c = TestClient(create_app())
    r = c.post(
        "/v1/validate-urls",
        json={
            "urls": [
                "not-a-url",
                "https://linkedin.com/jobs/view/123?utm_source=share&utm_medium=member_desktop",
                "ftp://example.com/x",
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 3
    assert body["results"][0]["ok"] is False
    assert body["results"][1]["ok"] is True
    assert body["results"][2]["ok"] is False
