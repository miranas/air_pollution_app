"""Router vozlišče – LLM odloči, kateri vir uporabiti."""

from langchain_openai import ChatOpenAI

from ai import config
from ai.state import AgentState

# LLM za router (DeepSeek, temperature=0 za determinizem)
_llm = ChatOpenAI(
    model=config.DEEPSEEK_MODEL,
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL,
    temperature=0,
)

# Prompt za klasifikacijo
ROUTER_PROMPT = """Si klasifikator vprašanj o kakovosti zraka v Sloveniji. Če vprašanje NI o kakovosti zraka, meritvah, dokumentih ali zakonodaji,
odgovori "splosno". Glede na vprašanje odloči, kateri vir uporabiti:

- "rag": vprašanja o dokumentih, zakonodaji, mejnih vrednostih,
         letnih poročilih, splošnih pojmih.
         Primeri: "Kaj je PM10?", "Kakšne so mejne vrednosti?",
                  "Kaj pravi Uredba o emisijah?"

- "sql": vprašanja o meritvah na specifičnih postajah ali v specifičnih
         obdobjih iz preteklosti, agregacijah (povprečja, maksimumi),
         primerjavah med postajami.
         Primeri: "Koliko meritev PM10 je bilo v Ljubljani leta 2024?",
                  "Katera postaja je imela najvišji NO2 v letu 2023?",
                  "Povprečje PM10 v Celju v januarju 2024?",
                  "Koliko NO2 je bilo včeraj v Novi Gorici?",
                  "Kdaj so večerni viški NOx?"

- "redis": vprašanja o trenutnih meritvah, zadnjih 24h, tem tednu,
           ta mesec, letos.
           Primeri: "Kakšno je danes onesnaženje v Ljubljani?",
                    "Kakšen je bil PM10 zadnjih 24h?",
                    "Kakšna je kakovost zraka ta teden?"
                    
- "splosno": pozdravi, vljudnostne fraze, vprašanja, ki niso povezana
             s kakovostjo zraka.
             Primeri: "Živjo, kako si?", "Hvala, nasvidenje!",
                      "Kdo si?", "Kaj znaš?", "Povej mi šalo.",
                      "Kakšno je vreme?", "Kdo je predsednik?",
                      "Pomagaj mi s kodo."

Vprašanje: {question}

Odgovori samo z eno besedo: rag, sql, splošno ali redis."""


def router_node(state: AgentState) -> AgentState:
    """
    Vozlišče router – LLM klasificira vprašanje.

    Vhod:  state["question"]
    Izhod: state["route"] = "rag" | "sql" | "redis" |"splosno"
    """
    question = state["question"]

    # Pokliči LLM
    prompt = ROUTER_PROMPT.format(question=question)
    response = _llm.invoke(prompt)
    raw_route = response.content.strip().lower()

    # Validacija: odstrani pike, presledke
    route = raw_route.strip(". ,!?:;")

    # Preveri, ali je v dovoljenih
    if route not in ("rag", "sql", "redis", "splosno"):
        # Če LLM vrne npr. "document", "measurement", "latest"
        if "rag" in route or "document" in route or "zakon" in route:
            route = "rag"
        elif "sql" in route or "measurement" in route or "meritev" in route:
            route = "sql"
        elif "redis" in route or "latest" in route or "trenut" in route:
            route = "redis"
        elif "splosno" in route or "splosno" in route or "chat" in route:
            route = "splosno"
        else:
            route = "splosno"  # default naj bo "splosno", ne "rag"

    state["route"] = route
    return state