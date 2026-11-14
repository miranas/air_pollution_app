"""Redis vozlišče – LLM izlušči periodo, nato pokliče redis_latest/redis_history."""

from langchain_openai import ChatOpenAI

from ai import config
from ai.state import AgentState
from ai.tools import redis_latest, redis_history
import json


# LLM za izluščitev periode (DeepSeek, temperature=0)
_llm = ChatOpenAI(
    model=config.DEEPSEEK_MODEL,
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL,
    temperature=0,

)


PERIOD_PROMPT = """Iz vprašanja ugotovi, katero periodo želi uporabnik:

- "latest": trenutne meritve (zdaj, trenutno)
- "day": danes, zadnjih 24h, včeraj
- "week": ta teden, zadnjih 7 dni
- "month": ta mesec, zadnjih 30 dni
- "year": letos, zadnjih 365 dni

Vprašanje: {question}

Odgovori samo z eno besedo: latest, day, week, month, ali year."""


def redis_node(state: AgentState) -> AgentState:
    """
    Vozlišče Redis – LLM izlušči periodo, nato pokliče redis_latest/redis_history.

    Vhod:  state["question"]
    Izhod: state["context"] = JSON z meritvami
    """
    question = state["question"]

    try:
        # 1. LLM izlušči periodo
        prompt = PERIOD_PROMPT.format(question=question)
        response = _llm.invoke(prompt)
        period = response.content.strip().lower().strip(". ,!?:;")

        # 2. Validacija
        if period not in ("latest", "day", "week", "month", "year"):
            period = "latest"   # default

        # 3. Pokliči ustrezno funkcijo
        if period == "latest":
            result = redis_latest()
        else:
            result = redis_history(period)
        # 3. Shrani periodo + rezultat
        state["context"] = json.dumps({
            "vprasanje": question,
            "perioda": period,
            "podatki": json.loads(result),
        }, ensure_ascii=False)
        state["error"] = None

    except Exception as e:
        state["context"] = ""
        state["error"] = f"Redis napaka: {e}"

    return state
