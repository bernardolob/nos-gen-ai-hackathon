from types import SimpleNamespace

from gemini import AuthenticationError
from gemini import cli


class FakeClient:
    error = None
    closed = False

    def __init__(self, _settings):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        type(self).closed = True

    def check_connection(self):
        if self.error:
            raise self.error
        return SimpleNamespace(requested_model="gemini-3.5-flash-lite")


def test_cli_reports_missing_configuration(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert cli.main([]) == 2
    output = capsys.readouterr()
    assert "GEMINI_API_KEY" in output.err


def test_cli_success_is_minimal(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "GeminiClient", FakeClient)

    assert cli.main([]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "gemini-3.5-flash-lite" in output.out
    assert "test-key" not in output.out
    assert FakeClient.closed


def test_cli_failure_is_sanitized(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    FakeClient.error = AuthenticationError("Authentication failed safely.")
    monkeypatch.setattr(cli, "GeminiClient", FakeClient)

    assert cli.main([]) == 3
    output = capsys.readouterr()
    assert "Authentication failed safely" in output.err
    assert "test-key" not in output.err
    FakeClient.error = None
