"""LangGraph orchestrator (TRD §7).

Graph shape:
    triage -> recall -> tools -> reasoner -> writer -> END

`triage` and `recall` run in sequence (triage is cheap; recall depends
on patient_id resolved upstream). Tools branch on intent. Writer is a
no-op for low-importance turns.

Checkpointing is via AsyncPostgresSaver so multi-turn voice + WhatsApp
sessions survive process restarts (TRD §10).
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from app.agents.recall import recall_node
from app.agents.reasoner import reasoner_node
from app.agents.state import AgentState
from app.agents.tools_node import tools_node
from app.agents.triage import triage_node
from app.agents.writer import writer_node
from app.config import get_settings

log = logging.getLogger(__name__)


def _route_after_recall(state: AgentState) -> str:
    """Route to the tools node when work is needed there.

    A pending action (a book/reschedule/cancel awaiting the patient's slot
    pick or confirmation) always routes to tools so a bare reply like "9am"
    or "yes" gets executed — even if triage scored it smalltalk/unknown.
    Otherwise only genuinely tool-less intents skip straight to the reasoner."""
    if state.get("pending"):
        return "tools"
    return "reasoner" if state.get("intent", "unknown") in {"smalltalk", "unknown"} else "tools"


async def build_graph(app_state):
    """Wire the state graph and bind a Postgres checkpointer.

    `app_state.exit_stack` must be an entered `AsyncExitStack`; we push
    the checkpointer onto it so shutdown closes the connection pool.
    """
    settings = get_settings()

    graph = StateGraph(AgentState)
    graph.add_node("triage", triage_node)
    graph.add_node("recall", recall_node)
    graph.add_node("tools", tools_node)
    graph.add_node("reasoner", reasoner_node)
    graph.add_node("writer", writer_node)

    graph.add_edge(START, "triage")
    graph.add_edge("triage", "recall")
    graph.add_conditional_edges("recall", _route_after_recall, {"tools": "tools", "reasoner": "reasoner"})
    graph.add_edge("tools", "reasoner")
    graph.add_edge("reasoner", "writer")
    graph.add_edge("writer", END)

    checkpointer = None
    if settings.database_url:
        cm = AsyncPostgresSaver.from_conn_string(settings.database_url)
        checkpointer = await app_state.exit_stack.enter_async_context(cm)
        await checkpointer.setup()
    else:
        log.warning("database_url not set; running without checkpointer")

    return graph.compile(checkpointer=checkpointer)
