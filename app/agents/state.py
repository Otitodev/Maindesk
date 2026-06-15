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
    # ISO 639-1 code of the patient's message, detected by triage ("en" default).
    language: str
    memories: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    reply: PatientReply
    escalated: bool
    session_cache: Any
    # Multi-turn action awaiting the patient's slot pick or yes/no confirmation
    # (book / reschedule / cancel). Persisted across turns by the checkpointer
    # so any channel can resume a flow mid-conversation. None when idle.
    pending: dict[str, Any] | None
    # LangGraph chat history channel (auto-merged across turns).
    messages: Annotated[list, add_messages]
