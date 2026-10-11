"""Shared pytest setup and fakes for the Gemini and API tests.

Puts ``submission/solution`` (the ``api`` package) and
``submission/solution/src`` (the ``gemini`` package) on the import path.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))
sys.path.insert(0, str(SOLUTION))


class FakeModels:
    def __init__(self):
        self.get_result = SimpleNamespace(
            name="models/gemini-3.5-flash-lite",
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        )
        self.get_error = None
        self.get_calls = []
        self.generate_result = SimpleNamespace(
            text="Hi from Gemini!",
            model_version="gemini-3.5-flash-lite",
        )
        self.generate_error = None
        self.generate_calls = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        if self.get_error:
            raise self.get_error
        return self.get_result

    def generate_content(self, **kwargs):
        self.generate_calls.append(kwargs)
        if self.generate_error:
            raise self.generate_error
        return self.generate_result


class FakeCaches:
    def __init__(self):
        self.create_result = SimpleNamespace(
            name="cachedContents/fake-cache-123"
        )
        self.create_error = None
        self.create_calls = []
        self.delete_error = None
        self.delete_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.create_error:
            raise self.create_error
        return self.create_result

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)
        if self.delete_error:
            raise self.delete_error


class FakeSdkClient:
    def __init__(self):
        self.models = FakeModels()
        self.caches = FakeCaches()
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


@pytest.fixture
def settings():
    from gemini import GeminiSettings

    return GeminiSettings(api_key="unit-test-key")


@pytest.fixture
def fake_sdk():
    return FakeSdkClient()
