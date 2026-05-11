from backend.core.env import EnvConfig


def test_invalid_fireworks_model_logs_warning(monkeypatch):
    monkeypatch.setenv("FIREWORKS_MODEL", "accounts/fireworks/models/not-real")
    monkeypatch.setenv("FIREWORKS_VISION_MODEL", "accounts/fireworks/models/not-real")
    seen: list[str] = []

    def fake_warning(msg, *args, **kwargs):
        seen.append(msg % args if args else str(msg))

    monkeypatch.setattr("backend.core.env.logger.warning", fake_warning)
    cfg = EnvConfig.load(strict=False)
    assert cfg.fireworks_model == "accounts/fireworks/models/not-real"
    combined = "\n".join(seen)
    assert "invalid_fireworks_model_configured" in combined
    assert "invalid_fireworks_vision_model_configured" in combined
