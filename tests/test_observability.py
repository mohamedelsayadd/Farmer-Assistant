from typing import Any

import pytest

import core.observability as observability
from conftest import build_settings


class Recorder:
    def __init__(self) -> None:
        self.langfuse_kwargs: dict[str, Any] = {}
        self.instrumented = False
        self.sdk_tracing_disabled: bool | None = None


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()

    def fake_langfuse(**kwargs: Any) -> object:
        recorder.langfuse_kwargs = kwargs
        return object()

    class FakeInstrumentor:
        def instrument(self) -> None:
            recorder.instrumented = True

    def fake_set_tracing_disabled(disabled: bool) -> None:
        recorder.sdk_tracing_disabled = disabled

    monkeypatch.setattr(observability, "Langfuse", fake_langfuse)
    monkeypatch.setattr(observability, "OpenAIAgentsInstrumentor", FakeInstrumentor)
    monkeypatch.setattr(observability, "set_tracing_disabled", fake_set_tracing_disabled)
    return recorder


def test_observe_flag_on_enables_langfuse_tracing(recorder: Recorder) -> None:
    observability.create_langfuse_client(build_settings(LANGFUSE_OBSERVE="true"))

    assert recorder.langfuse_kwargs["tracing_enabled"] is True
    assert recorder.instrumented is True
    assert recorder.sdk_tracing_disabled is None


def test_observe_flag_off_disables_all_tracing(recorder: Recorder) -> None:
    observability.create_langfuse_client(build_settings(LANGFUSE_OBSERVE="false"))

    assert recorder.langfuse_kwargs["tracing_enabled"] is False
    assert recorder.instrumented is False
    assert recorder.sdk_tracing_disabled is True


def test_observe_flag_on_without_credentials_stays_disabled(recorder: Recorder) -> None:
    observability.create_langfuse_client(
        build_settings(LANGFUSE_OBSERVE="true", LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")
    )

    assert recorder.langfuse_kwargs["tracing_enabled"] is False
    assert recorder.instrumented is False
    assert recorder.sdk_tracing_disabled is True
