from types import SimpleNamespace

import pytest

from nos_anonymizer import GeminiSettings


class FakeModels:
    def __init__(self):
        self.get_result = SimpleNamespace(
            name="models/gemini-3.5-flash",
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        )
        self.get_error = None
        self.get_calls = []
        self.generate_result = SimpleNamespace(
            text="Hi from Gemini!",
            model_version="gemini-3.5-flash",
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


class FakeSdkClient:
    def __init__(self):
        self.models = FakeModels()
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


@pytest.fixture
def settings():
    return GeminiSettings(api_key="unit-test-key")


@pytest.fixture
def fake_sdk():
    return FakeSdkClient()
