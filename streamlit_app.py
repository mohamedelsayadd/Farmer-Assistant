import os
from uuid import uuid4

import httpx
import streamlit as st


DEFAULT_API_BASE_URL = os.getenv("CHAT_API_BASE_URL", "http://localhost:8000")


def initialize_session() -> None:
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = str(uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []


def reset_conversation() -> None:
    st.session_state.conversation_id = str(uuid4())
    st.session_state.messages = []


def send_chat_message(api_base_url: str, jwt: str, conversation_id: str, message: str) -> str:
    endpoint = f"{api_base_url.rstrip('/')}/api/v1/chat"
    payload = {
        "jwt": jwt,
        "conversation_id": conversation_id,
        "message": message,
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        response_payload = response.json()
    return response_payload["message"]


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


def main() -> None:
    st.set_page_config(page_title="ReNile Farmer Assistant", page_icon="🌱")
    initialize_session()

    st.title("ReNile Farmer Assistant")
    st.caption("Simple Streamlit client for testing the FastAPI chat endpoint.")

    api_base_url, jwt, conversation_id = render_sidebar()
    render_chat_history()

    user_message = st.chat_input("اكتب رسالة للمساعد...")
    if not user_message:
        return

    if not jwt.strip():
        st.error("Please enter a JWT in the sidebar before sending a message.")
        return

    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        with st.spinner("المساعد بيرد..."):
            try:
                assistant_message = send_chat_message(
                    api_base_url=api_base_url,
                    jwt=jwt,
                    conversation_id=conversation_id,
                    message=user_message,
                )
            except httpx.HTTPStatusError as exc:
                assistant_message = f"Backend returned {exc.response.status_code}: {exc.response.text}"
                st.error(assistant_message)
            except httpx.HTTPError as exc:
                assistant_message = f"Could not reach backend: {exc}"
                st.error(assistant_message)
            else:
                st.markdown(assistant_message)

    st.session_state.messages.append({"role": "assistant", "content": assistant_message})


if __name__ == "__main__":
    main()
