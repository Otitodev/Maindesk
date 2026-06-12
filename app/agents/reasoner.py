"""Reasoning agent (TRD §7.3).

Qwen-Plus call that synthesises memories + tool results + the user
message into a reply. Tool execution is delegated to `tools_node`; this
node only produces text or signals an escalation.
"""

from __future__ import annotations

import logging

from app.agents.qwen_client import complete
from app.agents.state import AgentState
from app.config import get_settings
from app.gateway.schema import PatientReply

log = logging.getLogger(__name__)

_SYSTEM = """You are HealthDesk, a friendly front-desk assistant for a clinic.
Be brief, warm, and accurate.

Grounding rules — these are strict:
- If you do not know a clinic-specific fact (opening hours, address, phone,
  doctor names, prices, insurance accepted, services offered, parking, etc.),
  say "let me check and get back to you" or offer to connect them to staff.
  NEVER invent these facts.
- Only confirm appointment slots that appear in the Tool results block. If
  no slots are shown, say you'll check availability — do not make up times.
- Never give medical advice, diagnoses, or dosage guidance. For anything
  clinical, say you'll connect them to a clinician.
- If the patient's request needs human judgement, say you'll connect them
  to staff."""

# Canned escalation lines per detected language (the escalation path never
# reaches the LLM, so it can't translate itself). Fallback is English.
_ESCALATION_TEXT = {
    "en": "Let me connect you with one of our staff — one moment.",
    "es": "Permítame conectarle con nuestro personal — un momento.",
    "fr": "Je vous mets en relation avec notre personnel — un instant.",
    "pt": "Vou conectá-lo com a nossa equipe — um momento.",
    "ar": "سأقوم بتوصيلك بأحد موظفينا — لحظة من فضلك.",
    "zh": "我帮您转接我们的工作人员，请稍等。",
    "yo": "Jẹ́ kí n so ọ́ pọ̀ mọ́ òṣìṣẹ́ wa kan — ẹ dúró díẹ̀.",
    "ha": "Bari in haɗa ka da ma'aikacinmu — ɗan lokaci kaɗan.",
    "ig": "Ka m jikọọ gị na otu n'ime ndị ọrụ anyị — nwa oge.",
}


def _language_instruction(state: AgentState) -> str:
    lang = state.get("language") or "en"
    if lang == "en":
        return ""
    return (
        f"\n\nThe patient is writing in another language (ISO code: {lang})."
        f" Reply entirely in that language — do not switch to English."
    )


def _build_user_prompt(state: AgentState) -> str:
    msg = state.get("message")
    memories = state.get("memories") or []
    tool_results = state.get("tool_results") or []
    blocks: list[str] = []
    if memories:
        mem_lines = "\n".join(f"- {m.get('content','')}" for m in memories[:5])
        blocks.append(f"Relevant patient memory:\n{mem_lines}")
    if tool_results:
        tr = "\n".join(f"- {t}" for t in tool_results)
        blocks.append(f"Tool results:\n{tr}")
    blocks.append(f"Patient says: {msg.content if msg else ''}")
    return "\n\n".join(blocks)


async def reasoner_node(state: AgentState) -> AgentState:
    s = get_settings()
    msg = state.get("message")
    if msg is None:
        return {}

    if state.get("intent") == "escalate" or state.get("intent_confidence", 1.0) < s.escalation_confidence_threshold:
        lang = state.get("language") or "en"
        text = _ESCALATION_TEXT.get(lang, _ESCALATION_TEXT["en"])
        return {
            "reply": PatientReply(session_id=msg.session_id, channel=msg.channel, content=text),
            "escalated": True,
        }

    try:
        text = await complete(
            model=s.qwen_model_plus,
            system=_SYSTEM + _language_instruction(state),
            user=_build_user_prompt(state),
            temperature=0.3,
            max_tokens=400,
        )
    except Exception:
        log.exception("reasoner llm failed")
        text = "Sorry, I had a hiccup on my end. Could you say that again?"

    return {
        "reply": PatientReply(session_id=msg.session_id, channel=msg.channel, content=text),
    }
