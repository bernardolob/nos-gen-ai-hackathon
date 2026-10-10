import json
from types import SimpleNamespace

import pytest

from nos_anonymizer import GeminiSettings, TextBlock


class FakeModels:
    def __init__(self):
        self.get_result = SimpleNamespace(
            name="models/gemini-3.5-flash",
            input_token_limit=1_048_576,
            output_token_limit=65_536,
        )
        self.count_result = SimpleNamespace(total_tokens=42)
        self.get_error = None
        self.count_error = None
        self.get_calls = []
        self.count_calls = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        if self.get_error:
            raise self.get_error
        return self.get_result

    def count_tokens(self, **kwargs):
        self.count_calls.append(kwargs)
        if self.count_error:
            raise self.count_error
        return self.count_result


class FakeInteractions:
    def __init__(self):
        self.error = None
        self.calls = []
        self.result = completed_interaction()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeSdkClient:
    def __init__(self):
        self.models = FakeModels()
        self.interactions = FakeInteractions()
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def completed_interaction(entities=None, **overrides):
    values = {
        "status": "completed",
        "model": "gemini-3.5-flash",
        "output_text": json.dumps({"entities": entities or []}),
        "usage": SimpleNamespace(
            total_input_tokens=20,
            total_output_tokens=10,
            total_thought_tokens=None,
            total_tokens=30,
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def settings():
    return GeminiSettings(api_key="unit-test-key")


@pytest.fixture
def fake_sdk():
    return FakeSdkClient()


@pytest.fixture
def blocks():
    return (
        TextBlock(
            block_id="page:1",
            text="José: +351 912 345 678",
            metadata={"page": 1, "secret_adapter_note": "not transmitted"},
        ),
    )
