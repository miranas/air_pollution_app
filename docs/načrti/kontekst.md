 📋 KONTEKST ZA NOV CHAT – Air Pollution App

### Projekt

**Air Pollution App** – aplikacija za prikaz meritev kakovosti zraka iz ARSO (slovenske postaje). Prikazuje trenutne meritve in zgodovinske trende (dan, teden, mesec, leto). Ima tudi AI agenta (LangGraph + DeepSeek) za Q&A.

### Lokacije

- **Repo:** `~/Documents/air_pollution_app`
    
- **Produkcija:** Hetzner (`/opt/air_pollution_app`)
    
- **Obsidian vault:** `docs/` (odprt kot vault)
    

### Stack

- **Backend:** Flask (zdaj), **v migraciji na FastAPI** (async)
    
- **Baza:** PostgreSQL 17 (pgvector)
    
- **Cache:** Redis 7
    
- **Frontend:** Next.js
    
- **AI:** LangGraph + DeepSeek (RAG, SQL, Redis)
    
- **Docker:** docker-compose (nginx, backend, redis, postgres, prometheus, grafana, portainer, ollama)
    

### Kaj je bilo narejeno (oktober 2026)

|Kaj|Status|
|---|---|
|Diagnostika `/api/history` (omrežje, volumen, časovni pas, Flask kontekst)|✅ Rešeno|
|`TZ=Europe/Ljubljana` v `docker-compose.yml`|✅ Rešeno|
|Archflow diagram (`docs/arhitektura/archflow/architecture-report.html`)|✅ Dela|
|Skripta `archflow.sh` (generiranje + animacija + odpri brskalnik)|✅ Dela|
|Obsidian struktura (`docs/`)|✅ Vzpostavljeno|
|Kanban (4 stolpci)|✅ Vzpostavljeno|
|Dnevnik diagnostike|✅ Začet|
|`timestamptz` migracija|⏳ **Ni narejena** (odloženo)|
|FastAPI migracija|⏳ **Ni narejena** (načrt pripravljen)|

### Ključne ugotovitve (archflow)

1. LangGraph agent je **CLI-only** – Flask **nima** `/api/ask`.
    
2. Dva agent runtime-a: `ai/graph.py` (primarni) in `ai/agent.py` (legacy).
    
3. SQL varnost: read-only role + SELECT-only guard + LIMIT 100.
    
4. `/api/latest` uporablja 5-stopenjsko cache fallback lestvico.
    
5. AQI matematika podvojena (Python + TypeScript) → kandidat za reuse.
    
6. CI referencira `docker/Dockerfile.api`, ki ga ni v repozitoriju.
    

### Načrt: FastAPI + migracija baze (3 tedni)

**Dan 1 (danes):** Naroči Arduino + senzorje (ESP32, RAK3172, SPS30, SCD40, ~110 €)

**Dnevi 2–3:** Async infrastruktura

- `backend/database.py` – `create_async_engine`, `async_sessionmaker`
    
- `backend/dependencies.py` – `get_db`, `get_redis`
    
- `backend/main.py` – `FastAPI(title="Air Pollution API")`
    
- Preveri `uvicorn backend.main:app --reload --port 8000` → `/docs`
    

**Dnevi 4–5:** Pretvorba endpointov

- `/api/latest` → async (`await db.execute(select(...))`)
    
- `/api/history` → async (Redis cache + `build_history_payload_from_db_async`)
    

**Dan 6:** Migracija baze (`timestamptz`)

- Backup: `pg_dump -U airquality_user -d postgres > backup.sql`
    
- `ALTER TABLE measurements ALTER COLUMN measured_at TYPE timestamptz USING measured_at AT TIME ZONE 'Europe/Ljubljana';`
    
- Popravi model (`DateTime(timezone=True)`), parser (`tzinfo=ZoneInfo("Europe/Ljubljana")`), poizvedbe (`datetime.now(timezone.utc)`)
    

**Dnevi 7–8:** Testi

- `tests/conftest.py` – `AsyncClient` + `ASGITransport`
    
- `tests/test_api.py` – 10–15 testov
    
- `pytest tests/ -v`
    

**Dnevi 9–10:** SSL + domena

- Kupi domeno, DNS → Hetzner IP, `certbot --nginx`
    

**Dnevi 11–14:** Arduino (ko pride)

- Sestavi (ESP32 + SPS30 + SCD40 + RAK3172)
    
- Testiraj surove podatke (Serial)
    
- WiFi test: `HTTP POST` na `/api/sensors`
    
- LoRaWAN test: TTN → Webhook → `/api/sensors`
    

**Dnevi 15–21:** Frontend + AI + deployment

- React update (prikaz podatkov s senzorjev)
    
- AI evaluation (če zmanjka časa, prestavi)
    
- Docker compose (uvicorn namesto gunicorn)
    
- Produkcijski deployment
    

### Kaj **ne** delaj

|Ne delaj|Zakaj|
|---|---|
|WebSockets|Polling je dovolj|
|Alembic|Ročni `ALTER TABLE` je dovolj|
|Avtentikacija|Javna aplikacija|
|Pydantic modeli za vsak response|Ni nujno – `dict` je dovolj|
|Async SQLAlchemy v `async def` s sinhronim klicem|Blokira event loop|
|`current_app`|Zamenjaj z `Depends`|

### Arduino + senzorji (naročilo)

|Kos|Cena|Zakaj|
|---|---|---|
|**ESP32**|~10 €|WiFi + procesiranje|
|**RAK3172** (LoRaWAN)|~20 €|Produkcija (domet, poraba)|
|**SPS30** (Sensirion)|~40 €|PM1/2.5/4/10, MCERTS|
|**SCD40** (Sensirion)|~30 €|CO2 + temp/vlaga, NDIR|
|**Breadboard + žice**|~10 €|Povezava|
|**Skupaj**|**~110 €**||

**Opcijsko:** RAK7268V2 gateway (~229 €), ampak za testno fazo **ne rabiš** – TTN v Ljubljani pokriva (12 gatewayev).

### Povezava Arduino → FastAPI

- **Testna faza:** WiFi (ESP32) → `HTTP POST` na `/api/sensors`
    
- **Produkcija:** LoRaWAN (RAK3172) → TTN → Webhook → `/api/sensors`
    

### Dokumentacija (docs/)

text

docs/
├── arhitektura/archflow/          # Archflow diagram + skripta
│   ├── architecture-report.html
│   ├── architecture-report.hero.json
│   ├── architecture-report.template.html
│   └── archflow.sh
├── 01-projekti/air-pollution-app/
│   ├── 00-pregled.md
│   ├── 01-arhitektura.md
│   ├── 03-dnevnik-diagnostike.md
│   └── 04-kanban.md
├── 02-znanje/slovar/              # TZ, timestamptz, app-context, docker-network
├── 04-dnevnik/                    # Dnevni zapisi
└── 05-načrti/                     # Freelance, profi stack

### Ključne lekcije

- `timestamp without time zone` je krhka izbira – ob spremembi `TZ` se interpretacija spremeni.
    
- `current_app` zahteva Flask kontekst – brez `app.app_context()` `_get_redis_client()` vrne `None`.
    
- V `docker-compose.yml` vedno nastavi `TZ=Europe/Ljubljana` v vseh storitvah, ki delajo s časi.
    
- `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` – relativne poti za prenosljivost.
    
- `PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"` – koren projekta iz lokacije skripte.
    

### Kaj sledi (prvi korak v novem chatu)

1. **Potrdi načrt** (zgoraj).
    
2. **Naroči Arduino + senzorje** (ESP32, RAK3172, SPS30, SCD40).
    
3. **Začni z Dan 1** – namesti pakete, ustvari `backend/database.py`, `backend/dependencies.py`, `backend/main.py`.
    
4. **Preveri** `uvicorn backend.main:app --reload --port 8000` → `/docs`.