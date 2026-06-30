import base64
import logging

from fastapi import Request

from models.schemas.chat import ChatResponse
from providers.text_to_speech import TextToSpeechError

logger = logging.getLogger(__name__)


async def add_voice_response(request: Request, response: ChatResponse) -> None:
    try:
        wav_bytes = await request.app.state.text_to_speech.synthesize_wav(response.message)
    except TextToSpeechError:
        logger.warning("voice_response_tts_failed conversation_id=%s", response.conversation_id, exc_info=True)
        return

    response.audio_wav_base64 = base64.b64encode(wav_bytes).decode("ascii")
    response.audio_content_type = "audio/wav"
