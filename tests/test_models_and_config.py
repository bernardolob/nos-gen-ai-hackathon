import pytest
from pydantic import ValidationError

from nos_anonymizer import (
    ConfigurationError,
    EntityCategory,
    GeminiSettings,
    TextBlock,
)
from nos_anonymizer.models import SensitiveEntity


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "environment-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("GEMINI_RETRY_ATTEMPTS", "4")

    settings = GeminiSettings()

    assert settings.api_key.get_secret_value() == "environment-key"
    assert settings.timeout_seconds == 12.5
    assert settings.retry_attempts == 4
    assert "environment-key" not in repr(settings)


def test_settings_require_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        GeminiSettings()


def test_from_env_sanitizes_configuration_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-that-must-not-leak")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "invalid")

    with pytest.raises(ConfigurationError) as caught:
        GeminiSettings.from_env()

    assert "key-that-must-not-leak" not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", 0),
        ("retry_attempts", 0),
        ("retry_initial_delay_seconds", -1),
        ("retry_max_delay_seconds", 121),
        ("retry_max_delay_seconds", 0.5),
    ],
)
def test_settings_reject_invalid_operational_values(field, value):
    with pytest.raises(ValidationError):
        GeminiSettings(api_key="test", **{field: value})


@pytest.mark.parametrize(
    "values",
    [
        {"block_id": "", "text": "content"},
        {"block_id": " padded ", "text": "content"},
        {"block_id": "ok", "text": "   "},
        {"block_id": "bad\nidentifier", "text": "content"},
    ],
)
def test_text_block_rejects_invalid_values(values):
    with pytest.raises(ValidationError):
        TextBlock(**values)


def test_sensitive_values_are_hidden_from_repr():
    block = TextBlock(block_id="one", text="private", metadata={"source": "x"})
    entity = SensitiveEntity(
        block_id="one",
        start_char=0,
        end_char=7,
        text="private",
        category=EntityCategory.OTHER_PERSONAL_IDENTIFIER,
        reason="Direct identifier",
    )

    assert "private" not in repr(block)
    assert "private" not in repr(entity)
