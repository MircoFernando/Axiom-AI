"""Messaging domain models — inbound jobs and identity context."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IdentityContext(BaseModel):
    """Resolved caller identity — carried queue → worker → RAG."""

    role: Literal["student", "staff", "unknown"] = "student"
    tenant_id: str
    student_id: str | None = None
    staff_id: str | None = None
    class_ids: list[str] = Field(default_factory=list)


class InboundMessageJob(BaseModel):
    """Redis queue payload for one inbound WhatsApp message."""

    message_id: str
    from_phone: str
    text: str
    received_at: float
    channel: Literal["whatsapp"] = "whatsapp"
    identity: IdentityContext
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
