"""Shared LangGraph state (TRD §7)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

from app.gateway.schema import PatientMessage, PatientReply

Intent = Literal[
    "book_appointment",
    "reschedule",
    "cancel",
    "ask_question",
    "escalate",
    "smalltalk",
    "unknown",
]


class AgentState(TypedDict, total=False):
    message: PatientMessage
    intent: Intent
    intent_confidence: float
    memories: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    reply: PatientReply
    escalated: bool
    session_cache: Any
    # LangGraph chat history channel (auto-merged across turns).
    messages: Annotated[list, add_messages]
