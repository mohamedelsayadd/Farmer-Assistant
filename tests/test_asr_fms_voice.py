import httpx
import pytest

from conftest import build_settings
from providers.ASR.interface import ASRError, ASRUnsupportedAudioError
from providers.ASR.providers.fms_voice import FMSVoiceASRProvider

TRANSCRIPT = "درجة الحرارة كام؟"


def make_provider(handler, **overrides: str) -> FMSVoiceASRProvider:
    provider = FMSVoiceASRProvider(build_settings(ASR_PROVIDER="fms_voice", **overrides))
    # Swap the real client for a MockTransport one so no socket is ever opened.
    provider._build_client = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://asr.test",
        timeout=1,
    )
    return provider


def responder(status_code: int, json_body=None, text_body: str | None = None):
    """Build a handler that always answers the same way and records every request."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        requests.append(request)
        if text_body is not None:
            return httpx.Response(status_code, text=text_body)
        return httpx.Response(status_code, json=json_body)

    return handler, requests


async def test_transcribe_returns_the_service_text() -> None:
    handler, requests = responder(200, {"text": f" {TRANSCRIPT} ", "language": "ar", "rtfx": 14.47})
    provider = make_provider(handler)

    assert await provider.transcribe_wav(b"fake-audio") == TRANSCRIPT

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/transcribe"
    body = request.content
    assert b'name="file"' in body
    assert b"fake-audio" in body
    assert b'name="language"' in body
    assert b"ar" in body


async def test_transcribe_returns_empty_text_without_raising() -> None:
    # A blank transcript is a valid answer; the endpoint turns it into a 422.
    handler, _ = responder(200, {"text": "", "language": "ar"})

    assert await make_provider(handler).transcribe_wav(b"fake-audio") == ""


async def test_transcribe_omits_the_language_when_it_is_not_configured() -> None:
    handler, requests = responder(200, {"text": TRANSCRIPT})
    provider = make_provider(handler, ASR_LANGUAGE="")

    await provider.transcribe_wav(b"fake-audio")

    assert b'name="language"' not in requests[0].content


@pytest.mark.parametrize(
    "handler",
    [
        responder(200, text_body="not json")[0],
        responder(200, {})[0],
        responder(200, {"text": 42})[0],
    ],
)
async def test_transcribe_rejects_a_malformed_body(handler) -> None:
    # A broken contract is a terminal failure, not a decodable-audio problem.
    with pytest.raises(ASRError) as exc_info:
        await make_provider(handler).transcribe_wav(b"fake-audio")

    assert not isinstance(exc_info.value, ASRUnsupportedAudioError)


async def test_transcribe_raises_unsupported_audio_on_415() -> None:
    handler, _ = responder(415, {"detail": "Not decodable as audio"})

    with pytest.raises(ASRUnsupportedAudioError) as exc_info:
        await make_provider(handler).transcribe_wav(b"fake-audio")

    assert isinstance(exc_info.value, ASRError)


@pytest.mark.parametrize("status_code", [400, 404, 413, 422, 429, 500, 502, 503, 504])
async def test_transcribe_raises_asr_error_for_every_other_status(status_code: int) -> None:
    handler, requests = responder(status_code, {"detail": "nope"})

    with pytest.raises(ASRError) as exc_info:
        await make_provider(handler).transcribe_wav(b"fake-audio")

    assert not isinstance(exc_info.value, ASRUnsupportedAudioError)
    # No retry loop: one upstream call per transcription.
    assert len(requests) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
async def test_transcribe_raises_asr_error_when_the_service_is_unreachable(error: Exception) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(ASRError) as exc_info:
        await make_provider(handler).transcribe_wav(b"fake-audio")

    assert not isinstance(exc_info.value, ASRUnsupportedAudioError)


async def test_load_model_is_a_no_op() -> None:
    handler, requests = responder(200, {"text": TRANSCRIPT})

    await make_provider(handler).load_model()

    assert requests == []


def test_provider_rejects_an_unsupported_language() -> None:
    with pytest.raises(ValueError, match="Unsupported ASR_LANGUAGE for the fms_voice provider: fr"):
        FMSVoiceASRProvider(build_settings(ASR_PROVIDER="fms_voice", ASR_LANGUAGE="fr"))
