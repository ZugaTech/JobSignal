"""Central configuration contract for all environment variables."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class EnvVarSpec:
    name: str
    cast: Callable[[str], Any]
    default: Any
    description: str
    required: bool = False


def _as_bool(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _as_int(v: str) -> int:
    return int(v)


ENV_SPECS: tuple[EnvVarSpec, ...] = (
    EnvVarSpec("NODE_ENV", str, "development", "Runtime environment: development|staging|production"),
    EnvVarSpec("PORT", _as_int, 8080, "HTTP server port for deployment targets"),
    EnvVarSpec("ALLOWED_ORIGINS", str, "*", "Comma-separated CORS origins"),
    EnvVarSpec("LOG_LEVEL", str, "info", "Log level: debug|info|warning|error"),
    EnvVarSpec(
        "PROBE_PROVIDERS_ON_READY",
        _as_bool,
        False,
        "When true, /ready performs live Fireworks and Serper probes; when false, only config/cache checks run",
    ),
    EnvVarSpec("CACHE_DEFAULT_TTL_DAYS", _as_int, 14, "Shared cache TTL in days"),
    EnvVarSpec("SOURCE_PIPELINE_VERSION", str, "1", "Pipeline contract version"),
    EnvVarSpec("SCORER_VERSION", str, "1", "Scoring ruleset version"),
    EnvVarSpec("CACHE_URL", str, None, "Optional Redis URL; when absent, in-memory cache is used"),
    EnvVarSpec("FETCH_MAX_BYTES", _as_int, 2_097_152, "Max bytes to read from remote fetched posting pages"),
    EnvVarSpec("FETCH_MAX_REDIRECTS", _as_int, 5, "Max redirect hops while fetching posting pages"),
    EnvVarSpec("ENABLE_JOB_FETCH", _as_bool, False, "Enable live job page fetch checks"),
    EnvVarSpec("ENABLE_LLM_SIGNALS", _as_bool, False, "Enable LLM-based text signal extraction"),
    EnvVarSpec("ENABLE_IMAGE_VERIFY", _as_bool, False, "Enable screenshot OCR/vision flow"),
    EnvVarSpec("RECOMMENDATIONS_ENABLED", _as_bool, False, "Enable similar-job recommendation flow by default"),
    EnvVarSpec("RECOMMENDATIONS_MAX", _as_int, 3, "Hard cap for similar-job cards returned to the UI"),
    EnvVarSpec(
        "RECOMMENDATIONS_CANDIDATE_POOL",
        _as_int,
        8,
        "Max candidate URLs to verify before trimming recommendations",
    ),
    EnvVarSpec(
        "RECOMMENDATIONS_MIN_VERIFY_SCORE",
        _as_int,
        70,
        "Minimum nested verify confidence_score (0-100) for similar-job recommendations",
    ),
    EnvVarSpec("MAX_UPLOAD_BYTES", _as_int, 5 * 1024 * 1024, "Max upload size for screenshot input bytes"),
    EnvVarSpec("IMAGE_MAX_BYTES", _as_int, 5 * 1024 * 1024, "Legacy alias for screenshot upload size limit"),
    EnvVarSpec("RATE_LIMIT_REQUESTS_PER_MINUTE", _as_int, 20, "Per-IP request quota per minute"),
    EnvVarSpec("RATE_LIMIT_BURST", _as_int, 5, "Per-IP additional burst allowance within a window"),
    EnvVarSpec("SEARCH_API_ENDPOINT", str, "https://serpapi.com/search.json", "SERP provider endpoint URL"),
    EnvVarSpec("SEARCH_TIMEOUT_S", _as_int, 5, "SERP request timeout in seconds"),
    EnvVarSpec("SEARCH_RETRY_COUNT", _as_int, 2, "SERP retry attempts"),
    EnvVarSpec("SEARCH_RATE_LIMIT_PER_MINUTE", _as_int, 60, "SERP provider request cap per minute"),
    EnvVarSpec("SERPER_API_KEY", str, None, "Primary Serper.dev provider API key"),
    EnvVarSpec("SERPAPI_API_KEY", str, None, "Fallback SerpApi provider API key"),
    EnvVarSpec("SEARCH_API_KEY", str, None, "Generic fallback search key"),
    EnvVarSpec("FIREWORKS_API_KEY", str, None, "Primary Fireworks API key"),
    EnvVarSpec("LLM_API_KEY", str, None, "Fallback LLM provider key"),
    EnvVarSpec("FIREWORKS_BASE_URL", str, "https://api.fireworks.ai/inference/v1", "Fireworks OpenAI-compatible base URL"),
    EnvVarSpec("FIREWORKS_MODEL", str, "accounts/fireworks/models/kimi-k2p6", "Text model id"),
    EnvVarSpec("FIREWORKS_VISION_MODEL", str, "accounts/fireworks/models/kimi-k2p6", "Vision model id"),
    EnvVarSpec("FIREWORKS_TIMEOUT_S", _as_int, 8, "LLM call timeout in seconds"),
    EnvVarSpec("FIREWORKS_RETRY_COUNT", _as_int, 2, "LLM retry attempts"),
    EnvVarSpec("PIPELINE_DEADLINE_S", _as_int, 18, "Hard cap for parallel evidence phase (seconds)"),
    EnvVarSpec(
        "LLM_SUMMARY_CONFIDENCE_THRESHOLD",
        _as_int,
        85,
        "Skip verdict LLM and use template when confidence_score meets threshold and verdict is APPLY or SKIP",
    ),
)


def env_contract_lines() -> list[str]:
    lines: list[str] = []
    for s in ENV_SPECS:
        default = "" if s.default is None else str(s.default)
        lines.append(f"# {s.description}")
        lines.append(f"{s.name}={default}")
        lines.append("")
    return lines


@dataclass(frozen=True, slots=True)
class AppConfig:
    values: dict[str, Any]

    @classmethod
    def load(cls) -> "AppConfig":
        values: dict[str, Any] = {}
        for spec in ENV_SPECS:
            raw = os.environ.get(spec.name)
            if raw is None or raw.strip() == "":
                if spec.required and spec.default is None:
                    raise ValueError(f"Missing required env var: {spec.name}")
                values[spec.name] = spec.default
                continue
            try:
                values[spec.name] = spec.cast(raw.strip())
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"Invalid {spec.name}: {type(e).__name__}") from e
        return cls(values=values)

    def get(self, name: str) -> Any:
        return self.values.get(name)


def validate_startup_config() -> AppConfig:
    from backend.core.response_contract import assert_no_demo_mode_in_production

    assert_no_demo_mode_in_production()
    cfg = AppConfig.load()
    node_env = str(cfg.get("NODE_ENV") or "development").lower()
    if node_env in ("production", "staging") and not cfg.get("CACHE_URL"):
        raise ValueError("CACHE_URL is required when NODE_ENV is production/staging")
    return cfg


def fail_fast_startup() -> AppConfig:
    try:
        return validate_startup_config()
    except ValueError as e:
        logging.error("startup_config_error: %s", str(e))
        raise SystemExit(1) from e
