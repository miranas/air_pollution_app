"""Splošno vozlišče – za pozdrave in vprašanja, ki niso o kakovosti zraka."""

from ai.state import AgentState


def splosno_node(state: AgentState) -> AgentState:
    """
    Vozlišče za splošna vprašanja – ni konteksta.

    Vhod:  state["question"]
    Izhod: state["context"] = "" (prazen)
    """
    state["context"] = ""
    state["error"] = None
    return state
