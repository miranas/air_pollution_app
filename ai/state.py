"""State za LangGraph agenta."""

from typing import TypedDict, Literal


# Dovoljene poti v grafu
Route = Literal["rag", "sql", "redis"]


class AgentState(TypedDict):
    """State, ki potuje skozi LangGraph graf."""
    
    question: str          # uporabnikovo vprašanje
    route: str             # "rag" | "sql" | "redis"
    context: str           # najdeni podatki (JSON string)
    answer: str            # končni odgovor
    error: str | None      # napaka, če je
