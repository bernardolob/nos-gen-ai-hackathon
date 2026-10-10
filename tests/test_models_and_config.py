import pytest
from pydantic import ValidationError

from nos_anonymizer import (
    ConfigurationError,
    GenerationResult,
    GeminiSettings,
    ModelInfo,
)


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


def test_model_info_is_strict_and_immutable():
    info = ModelInfo(
        requested_model="gemini-3.5-flash",
        provider_name="models/gemini-3.5-flash",
    )

    with pytest.raises(ValidationError):
        info.requested_model = "different"
    with pytest.raises(ValidationError):
        ModelInfo(
            requested_model="gemini-3.5-flash",
            provider_name="models/gemini-3.5-flash",
            unexpected=True,
        )


def test_generation_result_hides_text_from_repr():
    result = GenerationResult(model="gemini-3.5-flash", text="private answer")

    assert "private answer" not in repr(result)
