"""
Veterinary Advisor connection.

Connects to the Veterinary Advisor agent, which is hosted separately in a
Google Colab notebook and exposed via ngrok as a public A2A endpoint. Since
that setup is not always running, this module also defines the fallback
message Farm Manager should use when the connection genuinely fails.

IMPORTANT: The ngrok URL changes every time the Colab notebook is restarted.
Update VETERINARY_ADVISOR_URL in Streamlit Cloud's secrets (not this file)
before each demo session.
"""

import streamlit as st
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool

# The unavailability message is deliberately unconditional: it always leads
# with the honest notice + real-vet instruction, regardless of how severe the
# farmer's situation sounds. General guidance is generic (not disease-specific)
# since we don't want to offer unvalidated diagnostic reasoning without the
# Vet Advisor's KB and escalation checks behind it.
VET_UNAVAILABLE_MESSAGE = (
    "⚠️ **The Veterinary Advisor is currently unavailable.** "
    "If this is urgent, please contact a licensed veterinarian directly as soon as possible.\n\n"
    "In the meantime, here's some general guidance: isolate any birds showing symptoms, "
    "maintain strict biosecurity (disinfect equipment, limit visitor access), and monitor "
    "the rest of the flock closely for similar signs."
)


def get_veterinary_tool():
    """
    Builds the veterinary_advisor AgentTool, pointed at the current ngrok URL
    from Streamlit secrets. Returns None if the URL isn't configured or the
    agent card can't be resolved -- callers should handle None gracefully.
    """
    vet_url = st.secrets.get("VETERINARY_ADVISOR_URL", "").strip()

    if not vet_url:
        return None

    try:
        veterinary_advisor = RemoteA2aAgent(
            name="veterinary_advisor",
            description=(
                "A specialized veterinary advisor for poultry health. "
                "Use this agent when the farmer reports bird health issues, "
                "unusual mortality, or when veterinary consultation is needed."
            ),
            agent_card=f"{vet_url}/.well-known/agent-card.json",
            use_legacy=False,
        )
        return AgentTool(agent=veterinary_advisor)
    except Exception as e:
        # Card resolution can fail immediately if the URL is stale/unreachable.
        # Don't crash app startup over this -- Farm Manager should still load
        # and use the fallback message when the farmer actually asks a health question.
        st.session_state.setdefault("_vet_connection_error", str(e))
        return None
