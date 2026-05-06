import socket

import httpx
import pytest

from backend.core.env import EnvConfig
from backend.core.fetch_job_page import (
    assert_safe_request_url,
    job_fetch_enabled,
    run_job_page_fetch,
)


def test_job_fetch_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_JOB_FETCH", raising=False)
    assert job_fetch_enabled() is False
    cfg = EnvConfig.load(strict=False)
    out = run_job_page_fetch("https://example.com/job", cfg)
    assert out.attempted is False
    assert out.signals == []


def test_blocks_loopback_literal():
    with pytest.raises(ValueError, match="FETCH_SSRF"):
        assert_safe_request_url("http://127.0.0.1/job")


def test_blocks_private_literal():
    with pytest.raises(ValueError, match="FETCH_SSRF"):
        assert_safe_request_url("http://10.0.0.1/job")


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("ENABLE_JOB_FETCH", "1")
    return EnvConfig.load(strict=False)


def test_fetch_200_populates_signals(monkeypatch, cfg):
    def fake_gai(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return socket.getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_gai)

    body = b"<html><title>Job</title></html>" + b"x" * 300

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        return httpx.Response(200, content=body, headers={"content-type": "text/html; charset=utf-8"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=httpx.Timeout(5.0))
    out = run_job_page_fetch("https://example.com/jobs/1", cfg, client=client)
    assert out.attempted is True
    ids = [s["id"] for s in out.signals]
    assert "fetch_ok" in ids
    assert "domain_align" in ids
    assert any(s["id"] == "fetch_ok" and s["strength"] == "high" for s in out.signals)


def test_redirect_hop_validates_next_host(monkeypatch, cfg):
    def fake_gai(host, *args, **kwargs):
        public = {"a.example.com": "93.184.216.34", "b.example.com": "93.184.216.34"}
        if host in public:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (public[host], 0))]
        return socket.getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_gai)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "https://b.example.com/b"})
        return httpx.Response(200, content=b"<html>" + b"z" * 400, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=httpx.Timeout(5.0))
    out = run_job_page_fetch("https://a.example.com/a", cfg, client=client)
    assert out.attempted is True
    dom = next(s for s in out.signals if s["id"] == "domain_align")
    assert "same registrable domain" in dom["details"].lower()
