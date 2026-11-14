"""SQL vozlišče – LLM generira SQL, nato pokliče sql_query."""

from langchain_openai import ChatOpenAI
import json

from ai import config
from ai.state import AgentState
from ai.tools import sql_query


# LLM za SQL generiranje (DeepSeek, temperature=0)
_llm = ChatOpenAI(
    model=config.DEEPSEEK_MODEL,
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL,
    temperature=0,
)


# Shema baze za LLM
SQL_SCHEMA = """Tabele:
- measurements (id, station_id, pollutant_id, measured_at, value)
- stations (id, station_id, station_name, latitude, longitude)
- pollutants (id, name, unit)

Povezave:
- measurements.station_id → stations.id
- measurements.pollutant_id → pollutants.id

Onesnaževala (pollutants.name – V MALE ČRKE):
- 'co', 'o3', 'no2', 'so2', 'pm10', 'pm25', 'nox', 'benzen'
- Za PM2.5 uporabi 'pm25' (brez pike)
- Za PM10 uporabi 'pm10'

Postaje (stations.station_name):
- 'Nova Gorica' → 'NG Grčna' (uporabi LIKE '%NG%' ali '%Grčna%')
- 'Ljubljana' → 'LJ Bežigrad', 'LJ Celovška', 'LJ Vič' (uporabi LIKE '%LJ%')
- 'Maribor' → 'MB Titova', 'MB Vrbanski' (uporabi LIKE '%MB%')
- 'Celje' → 'CE bolnica', 'CE Ljubljanska' (uporabi LIKE '%CE%')
- 'Koper' → 'Koper'
- 'Novo mesto' → 'Novo mesto'


Primeri:
- "PM10" → pollutants.name = 'PM10'
- "Ljubljana" → stations.station_name LIKE '%Ljubljana%'
- "leta 2024" → measured_at >= '2024-01-01' AND measured_at < '2025-01-01'
- "včeraj" → measured_at >= CURRENT_DATE - INTERVAL '1 day'
- "zadnjih 7 dni" → measured_at >= CURRENT_DATE - INTERVAL '7 days'

Čas:
- "leta 2024" → measured_at >= '2024-01-01' AND measured_at < '2025-01-01'
- "včeraj" → measured_at >= CURRENT_DATE - INTERVAL '1 day' AND measured_at < CURRENT_DATE
- "zadnjih 7 dni" → measured_at >= CURRENT_DATE - INTERVAL '7 days'
- "januarja 2024" → measured_at >= '2024-01-01' AND measured_at < '2024-02-01'

"""


SQL_PROMPT = """Si strokovnjak za SQL. Pretvori vprašanje v SQL SELECT poizvedbo.

{schema}

Vprašanje: {question}

Pravila:
- Vrni SAMO SQL poizvedbo, brez razlage.
- Uporabi samo SELECT.
- Uporabi LIMIT, če ni agregacije (COUNT, AVG, MAX, MIN).
- Uporabi JOIN za povezave med tabelami.
- Uporabi slovenska imena onesnaževal (PM10, PM2.5, NO2, NOx, O3, CO, SO2).
- Za PM2.5 uporabi pollutants.name = 'PM2.5' (ali 'PM25', preveri).

SQL:"""


def sql_node(state: AgentState) -> AgentState:
    """
    Vozlišče SQL – LLM generira SQL, nato pokliče sql_query.

    Vhod:  state["question"]
    Izhod: state["context"] = JSON z rezultati SQL poizvedbe
    """
    question = state["question"]

    try:
        # 1. LLM generira SQL
        prompt = SQL_PROMPT.format(schema=SQL_SCHEMA, question=question)
        response = _llm.invoke(prompt)
        sql = response.content.strip()

        # 2. Odstrani morebitne markdown oznake
        sql = sql.replace("```sql", "").replace("```", "").strip()

        # 3. Pokliči sql_query
        result = sql_query(sql)

        # 3. Shrani SQL + rezultat v context
        state["context"] = json.dumps({
            "vprasanje": question,
            "sql": sql,
            "rezultat": json.loads(result),
        }, ensure_ascii=False)
        state["error"] = None


    except Exception as e:
        state["context"] = ""
        state["error"] = f"SQL napaka: {e}"

    return state
