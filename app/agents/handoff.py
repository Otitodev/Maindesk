"""After-hours handoff node.

When the clinic is open but the agent is in after-hours mode, we don't fully
handle the conversation: we log an escalation so staff pick it up, and reply
with a short, language-aware acknowledgement. Mirrors the canned multilingual
pattern in reasoner._ESCALATION_TEXT.
"""

from __future__ import annotations

import logging

from app.agents.state import AgentState
from app.gateway.schema import PatientReply
from app.tools import escalation

log = logging.getLogger(__name__)

_HANDOFF_TEXT = {
    "en": "Thanks for reaching out — our team is in right now and will get back to you shortly.",
    "es": "Gracias por escribirnos — nuestro equipo está disponible ahora y le responderá en breve.",
    "fr": "Merci de nous avoir contactés — notre équipe est là et vous répondra sous peu.",
    "pt": "Obrigado pelo contato — nossa equipe está disponível e responderá em breve.",
    "ar": "شكرًا لتواصلك — فريقنا متواجد الآن وسيرد عليك قريبًا.",
    "zh": "感谢您的联系，我们的团队现在在线，会尽快回复您。",
    "yo": "A dúpẹ́ pé o kàn sí wa — ẹgbẹ́ wa wà nísinsìnyí, wọn yóò dáhùn sí ọ láìpẹ́.",
    "ha": "Na gode da tuntuɓarmu — ƙungiyarmu na nan kuma za su mayar maka da amsa nan ba da daɗewa ba.",
    "ig": "Daalụ maka ịkpọtụrụ anyị — ndị otu anyị nọ ugbu a, ha ga-azaghachi gị n'oge na-adịghị anya.",
}


async def handoff_node(state: AgentState) -> AgentState:
    """Acknowledge + escalate during open hours under after-hours mode."""
    msg = state.get("message")
    if msg is None:
        return {}
    await escalation.notify_staff(msg, reason="after_hours_staffed")
    lang = state.get("language") or "en"
    text = _HANDOFF_TEXT.get(lang, _HANDOFF_TEXT["en"])
    return {
        "reply": PatientReply(session_id=msg.session_id, channel=msg.channel, content=text),
        "escalated": True,
    }
