import os
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_openai import ChatOpenAI

DB_URI = "postgresql://agent_readonly:Salomon12@127.0.0.1:5432/postgres"

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

if __name__ == "__main__":
    odgovor = agent.invoke({"input": "Ob katerih urah je v povprečju najvišja koncentracija NO2?"})
    print(f"\nODGOVOR: {odgovor['output']}")