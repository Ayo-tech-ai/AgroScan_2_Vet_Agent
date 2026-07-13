"""
AgroScan AI Farm Manager - Streamlit chat interface.
"""

import asyncio
import streamlit as st

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from a2a.client.errors import A2AClientError, A2AClientHTTPError, A2AClientTimeoutError

try:
    from google.adk.agents.remote_a2a_agent import AgentCardResolutionError
except ImportError:
    AgentCardResolutionError = A2AClientError  # fallback if this ADK version doesn't expose it separately

from agent_setup import build_farm_manager_agent
from veterinary_connection import VET_UNAVAILABLE_MESSAGE
from escalation_enforcement import enforce_escalation_label

st.set_page_config(page_title="AgroScan Farm Manager", page_icon="🐔", layout="centered")

APP_NAME = "agroscan_farm_manager"
USER_ID = "streamlit_farmer"

# Exceptions that specifically indicate the veterinary_advisor A2A connection
# failed, as opposed to some other unrelated error.
VET_CONNECTION_ERRORS = (A2AClientError, A2AClientHTTPError, A2AClientTimeoutError, AgentCardResolutionError)


def init_session():
    """Runs once per browser session. Builds the agent, runner, and ADK session,
    and stores them in st.session_state so they persist across Streamlit reruns."""
    if "initialized" in st.session_state:
        return

    agent = build_farm_manager_agent()
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    session_id = "session_1"
    asyncio.run(
        session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    )

    st.session_state.runner = runner
    st.session_state.session_id = session_id
    st.session_state.messages = []  # for rendering chat history in the UI
    st.session_state.initialized = True


def run_farm_manager(message: str) -> str:
    """Sends a message to Farm Manager and returns the (escalation-enforced,
    fallback-aware) response text."""
    runner = st.session_state.runner
    session_id = st.session_state.session_id

    try:
        events = asyncio.run(
            runner.run_debug(message, user_id=USER_ID, session_id=session_id, quiet=True, verbose=False)
        )
    except VET_CONNECTION_ERRORS:
        # The veterinary_advisor tool call failed specifically due to a
        # connectivity issue (ngrok tunnel down, Colab not running, etc.)
        return VET_UNAVAILABLE_MESSAGE
    except Exception as e:
        # Some other, unrelated failure -- surface honestly rather than
        # pretending it's a vet-connection issue.
        return f"⚠️ Something went wrong processing your request: {e}"

    final_event = events[-1] if events else None
    if final_event and final_event.content and final_event.content.parts:
        response = " ".join(part.text for part in final_event.content.parts if part.text)
    else:
        response = "No response was generated."

    response = enforce_escalation_label(events, response)
    return response


# ---- UI ----

init_session()

st.title("🐔 AgroScan AI Farm Manager")
st.caption("Your poultry farm management assistant")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("is_emergency"):
            st.error(msg["content"])
        elif msg.get("is_urgent"):
            st.warning(msg["content"])
        else:
            st.markdown(msg["content"])

if prompt := st.chat_input("Ask about your farm..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = run_farm_manager(prompt)

        is_emergency = response.strip().upper().startswith("**EMERGENCY**") or response.strip().upper().startswith("EMERGENCY")
        is_urgent = response.strip().upper().startswith("**URGENT**") or response.strip().upper().startswith("URGENT")

        if is_emergency:
            st.error(response)
        elif is_urgent:
            st.warning(response)
        else:
            st.markdown(response)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response,
        "is_emergency": is_emergency,
        "is_urgent": is_urgent,
    })
