#!/usr/bin/env python3
"""Push `.env` values into the linked Railway service (same keys the backend reads).

Run from repo root with Railway CLI logged in and service linked:

  python scripts/push_env_to_railway.py

Optional: apply variables with `--skip-deploy` per key (default), then trigger **one** redeploy:

  python scripts/push_env_to_railway.py --deploy

Does **not** print secret values. Requires `railway` on PATH.

Safety:
- Skips `PORT` (Railway sets this).
- Skips `VITE_API_BASE` (build-time; use Dockerfile/build args if you ever need it).
- If `NODE_ENV` is production/staging but `CACHE_URL` is empty, forces `NODE_ENV=development`
  so the container does not exit on startup (add Redis + CACHE_URL, then set production).
- Sets `JOBSIGNAL_SEARCH_FIXTURE_PATH` empty on Railway (fixtures must not run in cloud).
- Use `--no-delete` so empty values in `.env` do **not** remove existing Railway variables
  (always clears `JOBSIGNAL_SEARCH_FIXTURE_PATH` on the remote — cloud safety).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _railway_exe() -> str:
    return shutil.which("railway") or shutil.which("railway.cmd") or "railway"

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

SKIP_KEYS = frozenset({"PORT", "VITE_API_BASE"})
EXTRA_KEYS = frozenset({"SENTRY_DSN", "JOBSIGNAL_SEARCH_FIXTURE_PATH"})
# Always remove fixture path on Railway even with --no-delete (must never run fixtures in cloud).
FORCE_DELETE_WHEN_EMPTY = frozenset({"JOBSIGNAL_SEARCH_FIXTURE_PATH"})


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        out[k] = v
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local .env into Railway service variables.")
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="After setting variables, run one `railway service redeploy -y` (avoids per-variable deploy storms).",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help=(
            "Do not run `railway variable delete` for empty .env values (preserves Railway-only "
            "secrets like CACHE_URL). Exception: JOBSIGNAL_SEARCH_FIXTURE_PATH is always cleared."
        ),
    )
    args = parser.parse_args()

    if not ENV_PATH.is_file():
        print(f"Missing {ENV_PATH}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    from backend.core.config import ENV_SPECS

    data = _parse_dotenv(ENV_PATH)
    allowed = {s.name for s in ENV_SPECS} | EXTRA_KEYS

    cache_url = (data.get("CACHE_URL") or "").strip()
    node_env = (data.get("NODE_ENV") or "development").strip().lower()
    if node_env in ("production", "staging") and not cache_url:
        print(
            "Adjusting NODE_ENV→development for Railway (CACHE_URL empty; add Redis then set production).",
            file=sys.stderr,
        )
        data["NODE_ENV"] = "development"

    # Cloud must not use local search fixtures
    data["JOBSIGNAL_SEARCH_FIXTURE_PATH"] = ""

    exe = _railway_exe()
    for key in sorted(allowed):
        if key in SKIP_KEYS:
            continue
        if key not in data:
            continue
        val = data[key]
        if val == "":
            if args.no_delete and key not in FORCE_DELETE_WHEN_EMPTY:
                print(
                    f"Skip empty {key} (Railway value unchanged; omit --no-delete to clear remote)",
                    file=sys.stderr,
                )
                continue
            # Railway CLI rejects KEY=… with empty value; remove key from service if it exists
            d = subprocess.run(
                [exe, "variable", "delete", key],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )  # delete has no --skip-deploys; batch deletes are rare
            if d.returncode == 0:
                print(f"Cleared {key}", file=sys.stderr)
            # else: key was not set on Railway; ignore
            continue
        pair = f"{key}={val}"
        r = subprocess.run(
            [exe, "variable", "set", "--skip-deploys", pair],
            cwd=ROOT,
            capture_output=True,
            text=True,
            shell=False,
        )
        if r.returncode != 0:
            print(r.stderr or r.stdout or "railway variable set failed", file=sys.stderr)
            return r.returncode
        print(f"Set {key}", file=sys.stderr)

    print("Railway variables updated.", file=sys.stderr)

    if args.deploy:
        rd = subprocess.run(
            [exe, "service", "redeploy", "-y"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if rd.returncode != 0:
            print(rd.stderr or rd.stdout or "railway service redeploy failed", file=sys.stderr)
            return rd.returncode
        print("Triggered railway service redeploy.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
