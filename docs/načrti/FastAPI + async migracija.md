FastAPI + async migracija (senior izvedba)

### Faza 0: Priprava (preden se dotakneš kode)

**Cilj:** Varnostna mreža in jasna slika, kaj se bo spremenilo.

| Korak | Kaj                          | Zakaj                                                                              |                                                         |
| ----- | ---------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 0.1   | **Backup baze**              | `pg_dump -U airquality_user -d postgres > backup_pred_fastapi_$(date +%Y%m%d).sql` | Brez tega ne začni                                      |
| 0.2   | **Inventar endpointov**      | Zapiši vse Flask route (`/api/latest`, `/api/history`, kar je še)                  | Da veš, kaj migriraš                                    |
| 0.3   | **Inventar odvisnosti**      | `pip freeze > requirements_flask.txt`                                              | Da veš, kaj je bilo                                     |
| 0.4   | **Testi za obstoječi Flask** | 10–15 testov za kritične poti (status kode, JSON oblika)                           | Varnostna mreža – brez tega ne veš, ali si kaj pokvaril |
| 0.5   | **Preveri, da testi tečejo** | `pytest tests/ -v` → vsi zeleni                                                    | Izhodišče                                               |

**Senior pravilo:** Ne migriraj endpointa, za katerega nimaš testa. Test je pogodba, ki jo mora FastAPI izpolniti.

---

### Faza 1: Async infrastruktura (temej)

**Cilj:** FastAPI app teče, `get_db` in `get_redis` sta pripravljena, `/docs` dela.

|Korak|Kaj|Kje|Zakaj|
|---|---|---|---|
|1.1|**Namesti pakete**|`pip install fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg redis pytest pytest-asyncio httpx`|Async stack|
|1.2|**`backend/database.py`**|`create_async_engine`, `async_sessionmaker(expire_on_commit=False)`|`expire_on_commit=False` – sicer objektov ne moreš brati po komitu|
|1.3|**`backend/dependencies.py`**|`get_db` (`async with AsyncSessionLocal() as session`), `get_redis` (`redis.asyncio`)|`async with` – avtomatsko zapre session, prepreči leak|
|1.4|**`backend/main.py`**|`FastAPI(title="Air Pollution API", version="2.0")`|Vstopna točka|
|1.5|**Preveri**|`uvicorn backend.main:app --reload --port 8000` → `/docs`|Brez tega ne nadaljuj|

**Senior pravilo:** `get_db` in `get_redis` sta **edina** vira resnice za povezave. Nikoli ne ustvarjaj session/clienta v endpointu – vedno prek `Depends`.

---

### Faza 2: Migracija endpointov (en po en)

**Cilj:** Vsak endpoint migriran **posebej**, s testom, ki ga preveri.

|Korak|Kaj|Zakaj|
|---|---|---|
|2.1|**`/api/latest` → async**|`await db.execute(select(...))`, `.scalar_one_or_none()`, `.scalars().all()`|
|2.2|**Preveri s testom**|Isti test kot na Flasku – mora vrniti isto obliko|
|2.3|**`/api/history` → async**|Redis cache + `build_history_payload_from_db_async` (async poizvedbe)|
|2.4|**Preveri s testom**|Isti test kot na Flasku|
|2.5|**`current_app` → `Depends`**|V `history_cache.py` zamenjaj `current_app.extensions['redis_client']` z `Depends(get_redis)`|
|2.6|**Preveri vse teste**|`pytest tests/ -v` → vsi zeleni|

**Senior pravilo:** Migriraj **en endpoint naenkrat**. Ne "vse hkrati". Če `/api/latest` ne dela, ne nadaljuj na `/api/history`.

**Past:** `async def` endpoint, ki kliče **sinhroni** SQLAlchemy, blokira event loop. V testih morda deluje, v produkciji ubije zmogljivost. Uporabi `AsyncSession` in `await`.

---

### Faza 3: Migracija baze v `timestamptz`

**Cilj:** `measured_at` je `timestamptz`, `MAX(measured_at) < NOW()` vedno drži.

| Korak | Kaj                   | Zakaj                                                                                                                   |                                             |
| ----- | --------------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| 3.1   | **Backup**            | `pg_dump ... > backup_pred_timestamptz_$(date +%Y%m%d).sql`                                                             | Brez tega ne začni                          |
| 3.2   | **`ALTER TABLE`**     | `ALTER TABLE measurements ALTER COLUMN measured_at TYPE timestamptz USING measured_at AT TIME ZONE 'Europe/Ljubljana';` | Vsak naiven timestamp interpretira kot CEST |
| 3.3   | **Popravi model**     | `measured_at = Column(DateTime(timezone=True), nullable=False)`                                                         | SQLAlchemy mora vedeti, da je `timestamptz` |
| 3.4   | **Popravi parser**    | `datetime.strptime(...).replace(tzinfo=ZoneInfo("Europe/Ljubljana"))`                                                   | Parser mora vračati aware datetime          |
| 3.5   | **Popravi poizvedbe** | `datetime.now(timezone.utc)`                                                                                            | Ne `datetime.now()` (naiven)                |
| 3.6   | **Preveri**           | `SELECT MAX(measured_at), NOW() FROM measurements;` → `MAX < NOW`                                                       | Brez tega ne nadaljuj                       |
| 3.7   | **Počisti Redis**     | `redis-cli DEL history_payload:day history_payload:week history_payload:month history_payload:year`                     | Cache je zastarel                           |
| 3.8.  | Alembic               |                                                                                                                         |                                             |

**Senior pravilo:** Migracija baze je **nepovratna**. Backup je obvezen. Če gre kaj narobe, obnovi iz backupa in ponovi.

---

### Faza 4: Testi (async, produkcijsko)

**Cilj:** Testi pokrijejo kritične poti, tečejo async, so zeleni.

|Korak|Kaj|Zakaj|
|---|---|---|
|4.1|**`tests/conftest.py`**|`AsyncClient` + `ASGITransport(app=app)`|Brez pravega strežnika|
|4.2|**`tests/test_api.py`**|`/api/latest`, `/api/history`, neveljaven period|10–15 testov|
|4.3|**`pytest.ini`**|`asyncio_mode = auto`|Da ni treba vsakega testa označiti|
|4.4|**`pytest tests/ -v`**|Vsi zeleni|Brez tega ne nadaljuj|

**Senior pravilo:** Testi so **pogodba**. Če FastAPI ne prestane istih testov kot Flask, migracija ni končana.

---

### Faza 5: Produkcija (SSL, Docker, deployment)

**Cilj:** FastAPI teče v produkciji, SSL dela, Docker posodobljen.

|Korak|Kaj|Zakaj|
|---|---|---|
|5.1|**SSL + domena**|`certbot --nginx -d tvoja-domena.com`|Brez tega ni produkcije|
|5.2|**Docker posodobitev**|`gunicorn` → `uvicorn` (ali `hypercorn`)|FastAPI potrebuje ASGI strežnik|
|5.3|**Preveri**|`curl https://tvoja-domena.com/api/latest`|Mora vrniti JSON|
|5.4|**Preveri `/docs`**|`https://tvoja-domena.com/docs`|Swagger UI|

**Senior pravilo:** Produkcija ni "še en test". Je **zadnji korak**, ko so testi zeleni in migracija baze uspela.

---

## ⚠️ Kaj **ne** delaj (senior pravila)

| Ne delaj                                              | Zakaj                                                                                  |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **WebSockets**                                        | Polling je dovolj. WebSocket doda kompleksnost brez koristi.                           |
| **Avtentikacija**                                     | Javna aplikacija. Avtentikacija je 1–2 dni dela, ki ga ne rabiš.                       |
| **Pydantic modeli za vsak response**                  | `dict` je dovolj. Pydantic modeli so za validacijo **vhoda**, ne izhoda.               |
| **Async SQLAlchemy v `async def` s sinhronim klicem** | Blokira event loop. Uporabi `AsyncSession`.                                            |
| **`current_app`**                                     | V FastAPI ga ni. Uporabi `Depends`.                                                    |
| **Migracija vseh endpointov hkrati**                  | Migriraj **enega naenkrat**, s testom.                                                 |

---

## 📋 Povzetek – vrstni red

|Faza|Kaj|Rezultat|
|---|---|---|
|**0**|Backup + testi za Flask|Varnostna mreža|
|**1**|Async infrastruktura|`uvicorn` teče, `/docs` dela|
|**2**|Endpointi (en po en)|`/api/latest`, `/api/history` async|
|**3**|Migracija baze|`timestamptz`, `MAX < NOW`|
|**4**|Async testi|Vsi zeleni|
|**5**|SSL + Docker|Produkcija|

---

**Ključno:** To je **senior izvedba** – vsak korak preveri, preden greš naprej. Brez "big bang" migracije. Brez Alembica, WebSockets, avtentikacije. Samo tisto, kar rabiš. Ko končaš fazo 1, mi povej – nadaljevala bova s fazo 2.