from ai import config
from ai.tools import sql_query, rag_search, redis_latest, redis_history
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage

TOOLS = [sql_query, rag_search, redis_latest, redis_history]

def _get_llm():
    """Vrni DeepSeek LLM z orodji."""
    llm = ChatOpenAI(
        model=config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        temperature=0,
    )
    return llm.bind_tools(TOOLS)

def ask(question: str, max_iterations: int = 15) -> str:
    """
    Vprašaj agenta.

    Args:
        question: slovensko vprašanje.
        max_iterations: največje število krogov.

    Returns:
        Odgovor v slovenščini.
    """

    llm = _get_llm()
    messages = [HumanMessage(content=question)]

    for i in range(max_iterations):
        response = llm.invoke(messages)
        print(f"\n[ITERACIJA {i + 1}]")
        print(f"Content: {response.content[:100]}")
        print(f"Tool calls: {response.tool_calls}")
        messages.append(response)

        if not response.tool_calls:
            return response.content

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            print(f"  → Klic orodja: {tool_name}({tool_args})")

            tool_func = next((t for t in TOOLS if t.__name__ == tool_name), None)



            if tool_func is None:
                result = f"Neznano orodje: {tool_name}"
            else:
                try:
                    result = tool_func(**tool_args)
                except Exception as e:
                    result = f"Napaka: {e}"
                    print(f"  → Napaka: {e}")


            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
