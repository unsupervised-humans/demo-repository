"""extraction/tests/test_llm_client.py
Unit tests for shared/llm_client.py.

Covers:
- missing GROQ_API_KEY environment variable raises EnvironmentError
- get_llm_client successfully initializes when GROQ_API_KEY is present
- base URL conforms to default or environment override (GROQ_BASE_URL)
- model name conforms to default or environment override (GROQ_MODEL)
"""

import os
from unittest.mock import patch
import pytest

from shared.llm_client import get_llm_client, active_model, DEFAULT_MODEL, DEFAULT_BASE_URL


class TestLLMClient:
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises_error(self):
        """If GROQ_API_KEY is not in the environment, EnvironmentError must be raised."""
        with pytest.raises(EnvironmentError) as exc_info:
            get_llm_client()
        assert "GROQ_API_KEY environment variable is not set" in str(exc_info.value)

    @patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key_123"}, clear=True)
    def test_client_creation_default(self):
        """Client should successfully initialize with default settings."""
        client = get_llm_client()
        assert client.api_key == "gsk_test_key_123"
        assert str(client.base_url).rstrip("/") == DEFAULT_BASE_URL.rstrip("/")

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "gsk_test_key_123",
            "GROQ_BASE_URL": "https://custom.groq.com/v1",
        },
        clear=True,
    )
    def test_client_creation_custom_base_url(self):
        """Client should respect GROQ_BASE_URL override."""
        client = get_llm_client()
        assert str(client.base_url).rstrip("/") == "https://custom.groq.com/v1"

    @patch.dict(
        os.environ,
        {
            "GROQ_API_KEY": "gsk_test_key_123",
            "GROQ_MODEL": "custom-model-99b",
        },
        clear=True,
    )
    def test_client_creation_custom_model(self):
        """Calling get_llm_client with GROQ_MODEL should update the active model."""
        # import active_model again to get current global state
        import shared.llm_client

        client = get_llm_client()
        assert shared.llm_client.active_model == "custom-model-99b"
