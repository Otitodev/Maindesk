"""Memory recall node (TRD §7.2, §9.2-9.3).

Wraps memory.recall.recall_memories so it slots into the LangGraph.
"""

from __future__ import annotations

from app.agents.state import AgentState
from app.memory.recall import recall_memories


async def recall_node(state: AgentState) -> AgentState:
    msg = state["message"]
    if not msg.patient_id:
        return {"memories": []}
    memories = await recall_memories(
        patient_id=msg.patient_id,
        query=msg.content,
        top_k=5,
    )
    return {"memories": memories}
