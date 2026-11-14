"""CLI vstopna točka za agenta."""

import sys
import json

from ai.graph import build_graph


def ask(question: str) -> dict:
    """Poženi graf in vrni state."""
    graph = build_graph()
    
    # Začetni state
    initial_state = {
        "question": question,
        "route": "",
        "context": "",
        "answer": "",
        "error": None,
    }
    
    # Poženi graf
    result = graph.invoke(initial_state)
    return result


def main():
    """CLI vstopna točka."""
    if len(sys.argv) < 2:
        print("Uporaba: python3 -m ai.main \"<vprašanje>\"")
        print()
        print("Primeri:")
        print("  python3 -m ai.main \"Kaj so mejne vrednosti PM10?\"")
        print("  python3 -m ai.main \"Koliko NO2 je bilo včeraj v Novi Gorici?\"")
        print("  python3 -m ai.main \"Kakšno je danes onesnaženje v Ljubljani?\"")
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    
    print(f"Vprašanje: {question}")
    print()
    
    result = ask(question)
    
    print(f"Route:    {result.get('route', '?')}")
    print(f"Error:    {result.get('error', 'None')}")
    print()
    print(f"Odgovor:  {result.get('answer', '(brez odgovora)')}")


if __name__ == "__main__":
    main()
