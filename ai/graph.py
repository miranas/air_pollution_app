"""LangGraph graf – poveže vozlišča v celoto."""

from langgraph.graph import StateGraph, START, END

from ai.state import AgentState
from ai.nodes.router import router_node
from ai.nodes.rag import rag_node
from ai.nodes.sql import sql_node
from ai.nodes.redis import redis_node
from ai.nodes.splosno import splosno_node
from ai.nodes.answer import answer_node


def route_decision(state: AgentState) -> str:
    """Pogojna funkcija – vrne ime vozlišča glede na state["route"]."""
    return state["route"]


def build_graph():
    """Sestavi LangGraph graf."""
    graph = StateGraph(AgentState)

    # 1. Dodaj vozlišča
    graph.add_node("router", router_node)
    graph.add_node("rag", rag_node)
    graph.add_node("sql", sql_node)
    graph.add_node("redis", redis_node)
    graph.add_node("splosno", splosno_node)
    graph.add_node("answer", answer_node)

    # 2. Povezave
    graph.add_edge(START, "router")

    # 3. Pogojna povezava: router → rag | sql | redis | splosno
    graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "rag": "rag",
            "sql": "sql",
            "redis": "redis",
            "splosno": "splosno",
        },
    )

    # 4. Vsa vozlišča → answer
    graph.add_edge("rag", "answer")
    graph.add_edge("sql", "answer")
    graph.add_edge("redis", "answer")
    graph.add_edge("splosno", "answer")

    # 5. answer → END
    graph.add_edge("answer", END)

    # 6. Compile
    return graph.compile()
