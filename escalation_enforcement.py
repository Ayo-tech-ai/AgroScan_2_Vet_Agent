"""
Escalation label enforcement.

Farm Manager's LLM (Llama via Groq) sometimes paraphrases the veterinary_advisor
tool's raw response and drops the EMERGENCY/URGENT label in the process. This
module inspects the raw tool result directly and force-restores the label on
Farm Manager's final response if it was present in the raw result but missing
from the final text.

This is a code-level safety net -- it does not rely on the LLM choosing to
preserve the label correctly.
"""

import re

ESCALATION_LABEL_PATTERN = re.compile(r'\*{0,2}(EMERGENCY|URGENT)\*{0,2}', re.IGNORECASE)


def extract_escalation_label(text: str):
    """Scan text for an EMERGENCY or URGENT label. Returns the uppercase label if found, else None."""
    if not text:
        return None
    match = ESCALATION_LABEL_PATTERN.search(text)
    return match.group(1).upper() if match else None


def enforce_escalation_label(events, final_response: str) -> str:
    """
    Scans all events from a run for the raw veterinary_advisor tool result.
    If an escalation label was present there but is missing from the final
    relayed response, force-prepend it.

    Args:
        events: list[Event] returned from runner.run_debug() or equivalent.
        final_response: the text Farm Manager is about to show the farmer.

    Returns:
        The final_response, with the escalation label restored if it was dropped.
    """
    raw_vet_label = None

    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                fr = getattr(part, "function_response", None)
                if fr and getattr(fr, "name", None) == "veterinary_advisor":
                    raw_result = fr.response
                    raw_text = raw_result.get("result", "") if isinstance(raw_result, dict) else str(raw_result)
                    found_label = extract_escalation_label(raw_text)
                    if found_label:
                        raw_vet_label = found_label

    if raw_vet_label and not extract_escalation_label(final_response or ""):
        return f"**{raw_vet_label}**\n\n{final_response}"

    return final_response
