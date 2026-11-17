from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    classify_node,
    email_node,
    finalize_node,
    report_node,
    research_node,
    synthesize_node,
    unsupported_node,
)
from agent.state import AgentState


def _route_after_classify(state: AgentState) -> str:
    """Deterministic routing based on the validated action."""
    action = state.get("action", "unknown")
    return action if action in {"email", "report", "both"} else "unknown"


def _route_after_report(state: AgentState) -> str:
    """For 'both', generate the report first so it can be attached to the email."""
    return "email" if state.get("action") == "both" else "finalize"


def build_graph():
    """Build and compile the LangGraph state machine."""
    builder = StateGraph(AgentState)

    builder.add_node("classify", classify_node)
    builder.add_node("research", research_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("email", email_node)
    builder.add_node("report", report_node)
    builder.add_node("unsupported", unsupported_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "email": "email",
            "report": "research",
            "both": "research",
            "unknown": "unsupported",
        },
    )
    builder.add_edge("research", "synthesize")
    builder.add_edge("synthesize", "report")
    builder.add_conditional_edges(
        "report",
        _route_after_report,
        {"email": "email", "finalize": "finalize"},
    )
    builder.add_edge("email", "finalize")
    builder.add_edge("unsupported", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()
