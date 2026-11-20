import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    """State shared between the LangGraph nodes."""

    message: str
    data: str
    filename: str
    action_hint: str
    to: str
    subject: str
    body: str
    title: str
    content: str
    search_query: str
    sources: list[dict]
    citations: list[dict]
    action: str
    email_args: dict
    report_args: dict
    results: Annotated[list[str], operator.add]
    artifacts: Annotated[list[dict], operator.add]
    steps: Annotated[list[dict], operator.add]
    final: str
