import base64
import os
from uuid import uuid4

import httpx
import streamlit as st


DEFAULT_API_BASE_URL = os.getenv("CHAT_API_BASE_URL", "http://localhost:8001")


def initialize_session() -> None:
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = str(uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []


def reset_conversation() -> None:
    st.session_state.conversation_id = str(uuid4())
    st.session_state.messages = []


def send_chat_message(api_base_url: str, jwt: str, conversation_id: str, message: str) -> dict:
    endpoint = f"{api_base_url.rstrip('/')}/api/v1/chat"
    payload = {
        "jwt": jwt,
        "conversation_id": conversation_id,
        "message": message,
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()


def send_voice_message(api_base_url: str, jwt: str, conversation_id: str, wav_bytes: bytes) -> dict:
    endpoint = f"{api_base_url.rstrip('/')}/api/v1/chat"
    data = {
        "jwt": jwt,
        "conversation_id": conversation_id,
    }
    files = {"wav_file": ("voice.wav", wav_bytes, "audio/wav")}
    with httpx.Client(timeout=240.0) as client:
        response = client.post(endpoint, data=data, files=files)
        response.raise_for_status()
        return response.json()


def render_sidebar() -> tuple[str, str, str]:
    with st.sidebar:
        st.header("Test Settings")
        api_base_url = st.text_input("Backend URL", value=DEFAULT_API_BASE_URL)
        jwt = st.text_input("JWT", type="password")
        conversation_id = st.text_input("Conversation ID", value=st.session_state.conversation_id)
        st.session_state.conversation_id = conversation_id

        if st.button("New Conversation", use_container_width=True):
            reset_conversation()
            st.rerun()

        st.caption("JWT is sent only to the backend chat endpoint.")

    return api_base_url, jwt, conversation_id


def render_chat_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            audio_bytes = message.get("audio_bytes")
            if audio_bytes:
                st.audio(audio_bytes, format="audio/wav")


def main() -> None:
    st.set_page_config(page_title="ReNile Farmer Assistant", page_icon="🌱")
    initialize_session()

    st.title("ReNile Farmer Assistant")
    st.caption("Simple Streamlit client for testing the FastAPI chat endpoint.")

    api_base_url, jwt, conversation_id = render_sidebar()
    render_chat_history()

    voice_input = st.audio_input("Record a voice message")
    user_message = st.chat_input("اكتب رسالة للمساعد...")
    if not user_message and voice_input is None:
        return

    if not jwt.strip():
        st.error("Please enter a JWT in the sidebar before sending a message.")
        return

    is_voice_message = voice_input is not None
    display_message = "Voice message" if is_voice_message else user_message
    st.session_state.messages.append({"role": "user", "content": display_message})
    with st.chat_message("user"):
        st.markdown(display_message)
        if is_voice_message:
            st.audio(voice_input.getvalue(), format="audio/wav")

    with st.chat_message("assistant"):
        try:
            if is_voice_message:
                payload = send_voice_message(
                    api_base_url=api_base_url,
                    jwt=jwt,
                    conversation_id=conversation_id,
                    wav_bytes=voice_input.getvalue(),
                )
            else:
                payload = send_chat_message(
                    api_base_url=api_base_url,
                    jwt=jwt,
                    conversation_id=conversation_id,
                    message=user_message,
                )
            assistant_message = payload["message"]
            st.markdown(assistant_message)
            audio_wav_base64 = payload.get("audio_wav_base64")
            assistant_audio = base64.b64decode(audio_wav_base64) if audio_wav_base64 else None
            if assistant_audio:
                st.audio(assistant_audio, format=payload.get("audio_content_type", "audio/wav"))
        except httpx.HTTPStatusError as exc:
            assistant_message = f"Backend returned {exc.response.status_code}: {exc.response.text}"
            assistant_audio = None
            st.error(assistant_message)
        except httpx.HTTPError as exc:
            assistant_message = f"Could not reach backend: {exc}"
            assistant_audio = None
            st.error(assistant_message)

    st.session_state.messages.append({"role": "assistant", "content": assistant_message, "audio_bytes": assistant_audio})


if __name__ == "__main__":
    main()
