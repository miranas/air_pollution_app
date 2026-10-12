import os
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_openai import ChatOpenAI

DB_URI = "postgresql+psycopg2://agent_readonly:Salomon12@127.0.0.1:5432/postgres"

db = SQLDatabase.from_uri(
    DB_URI,
    include_tables=['measurements', 'pollutants', 'stations'],
    sample_rows_in_table_info=3
)

llm = ChatOpenAI(
    model="deepseek-chat",
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base="https://api.deepseek.com/v1",
    temperature=0
)

agent = create_sql_agent(
    llm=llm,
    db=db,
    agent_type="openai-tools",
    verbose=True,
    handle_parsing_errors=True
)

vprasanja = [
    "Za poletne mesece (junij, julij, avgust) izračunaj povprečni NO2 ob 21h, 22h, 23h in 0h za postajo NG Grčna posebej in za povprečje naslednjih mestnih postaj: LJ Bežigrad, LJ Celovška, LJ Vič, MB Titova, MB Vrbanski, CE bolnica, CE Ljubljanska, Koper, Kranj, Novo mesto, MS Cankarjeva, Trbovlje, Zagorje, Hrastnik, Ptuj. Prikaži tabelo z vrednostmi in razliko. Odgovori v slovenščini.",
    "Za poletne mesece (junij, julij, avgust) izračunaj povprečni ozon (o3) ob 21h, 22h, 23h in 0h za postajo NG Grčna posebej in za povprečje naslednjih mestnih postaj: LJ Bežigrad, LJ Celovška, LJ Vič, MB Titova, MB Vrbanski, CE bolnica, CE Ljubljanska, Koper, Kranj, Novo mesto, MS Cankarjeva, Trbovlje, Zagorje, Hrastnik, Ptuj. Prikaži tabelo z vrednostmi in razliko. Odgovori v slovenščini."
     "Za poletne mesece (junij, julij, avgust) izračunaj povprečni NO2 ob 21h, 22h, 23h in 0h za postajo NG Grčna posebej in za povprečje naslednjih mestnih postaj: LJ Bežigrad, LJ Celovška, LJ Vič, MB Titova, MB Vrbanski, CE bolnica, CE Ljubljanska, Koper, Kranj, Novo mesto, MS Cankarjeva, Trbovlje, Zagorje, Hrastnik, Ptuj. Prikaži tabelo z vrednostmi in razliko (mesta − Grčna). Odgovori v slovenščini."
"Kdaj, ob kateri uri so večerni viški nox in no2 v Novi Gorici in kdaj v drugih mesecih?"
    "Za vsako postajo posebej izračunaj povprečni NO2 ob 17h, 18h, 19h, 20h, 21h, 22h, 23h in 0h. Prikaži tabelo, kjer so vrstice postaje, stolpci pa ure. Razvrsti postaje po vrednosti ob 22h padajoče. Odgovori v slovenščini."
    "Za postaji NG Grčna in LJ Celovška izračunaj razmerje med NO2 in NOx (NO2/NOx) po urah med 17h in 0h. Prikaži tabelo, kjer so vrstice ure, stolpci pa postaje. Odgovori v slovenščini."
]

for vpr in vprasanja:
    print(f"\n{'='*70}")
    print(f"VPRAŠANJE: {vpr}")
    print('='*70)
    odgovor = agent.invoke({"input": vpr})
    print(f"\nODGOVOR: {odgovor['output']}\n")
