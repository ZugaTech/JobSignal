"""Canonical Fireworks serverless model id when ``FIREWORKS_MODEL`` / env is unset.

Keep this as the **single** default string for Kimi K2.6 so ``config.py``, LLM call
sites, and tests cannot drift.
"""

DEFAULT_FIREWORKS_MODEL = "accounts/fireworks/models/kimi-k2p6"
