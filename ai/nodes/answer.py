"""Answer vozlišče – LLM generira končni odgovor iz konteksta."""

from langchain_openai import ChatOpenAI

from ai import config
from ai.state import AgentState


# LLM za generiranje odgovora (DeepSeek, temperature=0.3 za malo kreativnosti)
_llm = ChatOpenAI(
    model=config.DEEPSEEK_MODEL,
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL,
    temperature=0.3,
)


# Prompt za RAG/SQL/Redis – z kontekstom
ANSWER_WITH_CONTEXT = """Si pomočnik za kakovost zraka v Sloveniji.
Odgovori na vprašanje v slovenščini, na podlagi naslednjih podatkov.

Vprašanje: {question}

Podatki:
{context}

Navodila:
- Odgovori kratko, natančno in v slovenščini.
- Uporabi samo podatke iz konteksta – ne izmišljuj si.
- Če podatki ne vsebujejo odgovora, povej, da nimaš dovolj informacij.
- Če so podatki JSON, jih pretvori v berljiv odgovor.
- Ne omenjaj, da si prejel JSON – samo odgovori.
"""


# Prompt za splošno – brez konteksta
ANSWER_WITHOUT_CONTEXT = """Si pomočnik za kakovost zraka v Sloveniji.
Odgovori na vprašanje v slovenščini.

Vprašanje: {question}

Navodila:
- Odgovori kratko in prijazno.
- Če je pozdrav, pozdravi nazaj.
- Če vprašanje ni povezano s kakovostjo zraka, odgovori splošno.
- Če ne veš, povej, da ne veš.
"""


def answer_node(state: AgentState) -> AgentState:
    """
    Vozlišče answer – LLM generira končni odgovor.

    Vhod:  state["question"], state["context"], state["error"]
    Izhod: state["answer"]
    """
    question = state["question"]
    context = state.get("context", "")
    error = state.get("error")

    # 1. Če je napaka, odgovori z napako
    if error:
        state["answer"] = (
            f"Prišlo je do napake pri iskanju podatkov: {error}. "
            f"Poskusite znova ali preoblikujte vprašanje."
        )
        return state

    # 2. Če ni konteksta (splosno), odgovori brez konteksta
    if not context or not context.strip():
        prompt = ANSWER_WITHOUT_CONTEXT.format(question=question)
    else:
        # 3. Če je kontekst, odgovori z kontekstom
        prompt = ANSWER_WITH_CONTEXT.format(
            question=question,
            context=context,
        )

    # 4. Pokliči DeepSeek
    try:
        response = _llm.invoke(prompt)
        state["answer"] = response.content.strip()
    except Exception as e:
        state["answer"] = f"Napaka pri generiranju odgovora: {e}"

    return state