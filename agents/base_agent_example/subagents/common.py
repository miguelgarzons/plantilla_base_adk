from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from google.adk.models import Gemini

from base_agent_example.integrations.mcp.toolset_factory import build_mcp_toolsets


@dataclass(frozen=True)
class AgentDependencies:
    model: Any
    receptor_mcp_toolsets: list[Any]


RECEPTOR_TOOL_FILTER = [
    "ZohoDesk_getAccessibleOrganizations",
    "ZohoDesk_getDepartments",
    "ZohoDesk_getDepartment",
    "ZohoDesk_listOfTickets",
    "ZohoDesk_searchTickets",
    "ZohoDesk_getTicket",
    "ZohoDesk_getTicketsByContact",
    "ZohoDesk_getTicketCommentHistory",
    "ZohoDesk_getTicketResolutionHistory",
]


def build_dependencies() -> AgentDependencies:
    model_name = os.getenv("AGENT_MODEL", "gemini-2.5-pro")
    if model_name.startswith("gemini/"):
        model_name = model_name.split("/", 1)[1]

    return AgentDependencies(
        model=Gemini(model=model_name),
        receptor_mcp_toolsets=build_mcp_toolsets(tool_filter=RECEPTOR_TOOL_FILTER),
    )
