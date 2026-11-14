# Kontekst projekta – Air Pollution App

## Kaj je projekt
AI sistem za analizo kakovosti zraka v Sloveniji.
- RAG + SQL agent za vprašanja o meritvah in dokumentih.
- Podatki: ARSO meritve (445.000+ vrstic), dokumenti (Uredba, ARSO poročila).

## Kje je kaj
- **Lokalno:** `~/Documents/air_pollution_app/`
- **Strežnik:** `/opt/air_pollution_app/`
- **Tunel:** `~/Documents/air_pollution_app/ssh_tunel.sh`
- **Venv:** `~/Documents/air_pollution_app/venv/` (Python 3.14)

## Struktura	
ai/
├── config.py # branje .env
├── db.py # get_rag_connection(), get_sql_connection()
├── tools.py # sql_query, rag_search, redis_latest, redis_history
├── agent.py # agent z orodji (DeepSeek)
├── test_agent.py # testi
├── rag/
│ ├── vectorize.py # vektorižacija
│ └── watcher.py # watchdog
└── nodes/
└── router.py # (kasneje)

text

## Kaj dela
- `ai/agent.py` – agent z orodji (SQL, RAG, Redis) – **DELA**
- `ai/rag/watcher.py` – spremlja `ai/rag_sources` – **DELA**
- `ai/rag/vectorize.py` – vektorižira – **DELA** (a PDF fragmenti preveliki)

## Trenutni problem
- PDF fragmenti so preveliki (> 2048 tokenov) → Ollama faila.
- Rešitev: `chunk_text()` – razdeli na 1500 znakov.

## Plan za naprej
1. Popravi `chunk_text()` v `vectorize.py`.
2. Vektorižiraj PDF (Uredba).
3. LangGraph + validator.
4. README + docs.
5. FastAPI endpoint.

## Ključne datoteke
- `.env` – skrivnosti (ni v gitu)
- `archive/requirements.txt` – odvisnosti
- `ai/rag_sources` – dokumenti (.txt, .pdf)

## Testi
- `python3 -m ai.test_agent` – test agenta
- `python3 -m ai.rag.watcher` – watchdog
- `python3 -m ai.rag.vectorize <file>` – vektorižiraj eno datoteko

## Strežnik
- SSH: `ssh Hetzner`
- Tunel: `ssh -L 11434:127.0.0.1:11434 -L 5432:127.0.0.1:5432 -L 6379:127.0.0.1:6379 Hetzner`
- Docker: Ollama, PostgreSQL, Redis, Nginx


Nadaljujeva projekt Air Pollution App. Tukaj je kontekst:
[prilepi CONTEXT.md]

Trenutni problem: PDF fragmenti preveliki. Popraviva chunk_text() v vectorize.py.

3. Priloži ai/rag/vectorize.py – da vidim trenutno stanje.
