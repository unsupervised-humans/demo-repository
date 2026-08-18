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
DEFAULT_MODEL = "openai/gpt-oss-20b"  # Fallback model (on separate quota from qwen)


def get_llm_client() -> OpenAI:
    """
    Return an OpenAI-compatible client pointed at the Groq endpoint.

    Raises
    ------
    EnvironmentError
        If GROQ_API_KEY is not set in the environment.
    """
    if not os.environ.get("GROQ_API_KEY"):
        # Load from .env if present
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.isfile(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY environment variable is not set. "
            "Export it or place GROQ_API_KEY=gsk_... in a .env file:\n"
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

# Compatibility aliases used by classifier and tests
GrokClient = OpenAI
LLMClientError = Exception
get_default_client = get_llm_client

