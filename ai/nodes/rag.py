"""RAG vozlišče – pokliče rag_search in shrani kontekst."""

from ai.state import AgentState
from ai.tools import rag_search
import json


def rag_node(state: AgentState) -> AgentState:
    """
    Vozlišče RAG – pokliče rag_search.
    
    Vhod:  state["question"]
    Izhod: state["context"] = JSON z najdenimi chunki
    """
    question = state["question"]
    
    try:
        # Pokliči rag_search (vrne JSON string)
        result = rag_search(question, top_k=5)
        state["context"] = json.dumps({
            "vprasanje": question,
            "chunki": json.loads(result),
        }, ensure_ascii=False)
        state["error"] = None

    except Exception as e:
        state["context"] = ""
        state["error"] = f"RAG napaka: {e}"
    
    return state


"""Data flow:

1. Graf pokliče router_node(state)
   → router_node prebere state["question"]
   → router_node zapiše state["route"] = "rag"
   → vrne state

2. Graf pogleda state["route"] = "rag"
   → graf ve, da mora iti v rag_node

3. Graf pokliče rag_node(state)
   → rag_node prebere state["question"]
   → rag_node POKLIČE rag_search(question)  ← TUKAJ se sproži iskanje
     tukaj najde chunke z visokim scorom
   → rag_node zapiše state["context"] = rezultat
   → vrne state

4. Graf pogleda, da je rag_node končan
   → graf gre v answer_node

5. Graf pokliče answer_node(state)
   → answer_node prebere state["question"] in state["context"]     
   → answer_node POKLIČE LLM  ← TUKAJ se generira odgovor - sestavi ga iz najdenih chunkov
   → answer_node zapiše state["answer"] = odgovor
   → vrne state

6. Graf gre v END
   → vrne state
"""
