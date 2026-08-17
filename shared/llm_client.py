"""
shared/llm_client.py
--------------------
Thin wrapper around the Groq API, compatible with the OpenAI SDK.

Usage (from any agent):
    from shared.llm_client import get_llm_client, DEFAULT_MODEL

    client = get_llm_client()
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[...],
    )

Environment variables
---------------------
GROQ_API_KEY   – required; never committed to source control.
GROQ_BASE_URL  – optional override (default: https://api.groq.com/openai/v1)
GROQ_MODEL     – optional model override (default: qwen/qwen3.6-27b)

Reusable by Harris (ingestion/classification) and Christy (orchestrator/summarisation)
without any changes to this file.
"""

import os

try:
    from openai import OpenAI
except ImportError as exc:
    raise ImportError(
        "openai package is required: pip install openai"
    ) from exc

# ── defaults ──────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "qwen/qwen3.6-27b"  # Groq model to use


def get_llm_client() -> OpenAI:
    """
    Return an OpenAI-compatible client pointed at the Groq endpoint.

    Raises
    ------
    EnvironmentError
        If GROQ_API_KEY is not set in the environment.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY environment variable is not set. "
            "Export it before running the extraction pipeline:\n"
            "  export GROQ_API_KEY=gsk_..."
        )

    base_url = os.environ.get("GROQ_BASE_URL", DEFAULT_BASE_URL)
    model_override = os.environ.get("GROQ_MODEL")
    if model_override:
        global active_model  # noqa: PLW0603
        active_model = model_override

    return OpenAI(api_key=api_key, base_url=base_url)


# Module-level convenience — updated by get_llm_client() if GROQ_MODEL is set.
active_model: str = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
