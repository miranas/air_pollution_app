#  Async/await in asyncio – razlaga z uporabo tvoje kode

Tvoja domneva je blizu, ampak ni točna – **`asyncio` ni "async input output"** v smislu tipkovnice. Je **"Asynchronous I/O"** – "asinhrono vhodno-izhodno" v smislu **čakanja na mrežo, disk, bazo**.

## 🔍 Kaj je problem, ki ga async rešuje

### Sinhrono (Flask) – **ena stvar naenkrat**

python

# Sinhrono: "čakaj, dokler ne konča"
def get_latest():
    data = db.query(...)         # ← 50 ms čakanja (baza)
    result = redis.get(...)      # ← 5 ms čakanja (Redis)
    return result

**Kaj se zgodi:**

|Čas|Kaj dela proces|
|---|---|
|0 ms|Začne DB query|
|**0–50 ms**|⛔ **Čaka** – nič ne dela, samo čaka|
|50 ms|Dobi rezultat, začne Redis|
|**50–55 ms**|⛔ **Čaka** – nič ne dela|
|55 ms|Vrne|

**Problem:** Med čakanjem **proces ne dela nič**. Če v tistem pride še 10 requestov, **vsi čakajo v vrsti**.

### Asinhrono (FastAPI) – **med čakanjem dela drugo**

python

# Asinhrono: "pošlji zahtevo in med čakanjem delaj drugo"

async def get_latest():
    data = await db.execute(...)   # ← await = "medtem delaj drugo"
    result = await redis.get(...)  # ← await = "medtem delaj drugo"
    return result

**Kaj se zgodi:**

|Čas|Kaj dela proces|
|---|---|
|0 ms|Pošlje DB query, **ne čaka** – gre naprej|
|0–50 ms|✅ **Sprejema druge requeste** (npr. `/health`)|
|50 ms|DB vrne rezultat, proces nadaljuje|
|50 ms|Pošlje Redis, **ne čaka** – gre naprej|
|50–55 ms|✅ **Sprejema druge requeste**|
|55 ms|Vrne odgovor|

**Rezultat:** V istih 55 ms **10 requestov** lahko dobi odgovor, ne samo eden.

## 🎯 Kaj je `await`

**`await` pomeni: "zdaj čakam na rezultat, ampak medtem lahko procesor dela drugo."**

python

result = await redis.get("key")
#         ^^^^^
# "Počakaj, da Redis vrne – ampak medtem naj procesor  sprejema druge requeste."

**`await` je dovoljen samo v `async def`** – ker samo tam Python ve, da gre za asinhrono funkcijo.

## 🎯 Kaj je `async def`

**`async def` pomeni: "ta funkcija lahko uporablja `await`."**

python

async def get_latest():        # ← async def
    data = await db.execute()   # ← await (dovoljen, ker je async def)
    return data

**Brez `async def`:**

python

def get_latest():              # ← navaden def
    data = await db.execute()   # ❌ SyntaxError

## 🎯 Kaj je "event loop"

**Event loop je "prometni policist"**, ki usmerja requestе.

text

┌─────────────────────────────────────────────┐
│ Event loop (en sam, teče v ozadju)          │
│                                             │
│  Request 1: await db  ──► [čaka]           │
│  Request 2: await redis ──► [čaka]         │
│  Request 3: await db  ──► [čaka]           │
│                                             │
│  Ko Request 1 dobi rezultat:                │
│  ──► nadaljuje z naslednjo vrstico          │
└─────────────────────────────────────────────┘

**Ključno:** Event loop je **en sam** – zato **nikoli ne smeš blokirati**. Če ena funkcija "zasede" event loop, **vsi ostali čakajo**.

## 🔍 Kaj je `asyncio.to_thread` – in zakaj ga rabiš

**`update_data()` je sinhrona funkcija** – uporablja `requests.get()`, `SessionLocal()`, sinhroni Redis. Če jo pokličeš neposredno v `async def`, **blokiraš event loop**.

python

async def get_latest():
    update_data()   # ⛔ BLOKIRA event loop za 0.5–2 s
    return ...

**`asyncio.to_thread` reši to:**

python

async def get_latest():
    await asyncio.to_thread(update_data)
    #     ^^^^^^^^^^^^^^^^^^^^^^^^
    #     "Poženi update_data v LOČENI NITI,
    #      da event loop ostane prost."
    return ...

**Kaj se zgodi:**

|Brez `to_thread`|S `to_thread`|
|---|---|
|`update_data()` teče v event loopu|`update_data()` teče v **ločeni niti**|
|Event loop **blokiran** 0.5 s|Event loop **prost** – sprejema requeste|
|`/api/history` čaka|`/api/history` dela normalno|

## 📊 Diagram – sync vs async vs to_thread

### Sinhrono (Flask)

text

Request 1: ████████████████ (0.5 s)
Request 2:                 ████████████████ (0.5 s)
Request 3:                                 ████████████████
Skupaj: 1.5 s

### Asinhrono (FastAPI, brez to_thread)

text

Request 1: ████████████████ (0.5 s) – blokira event loop
Request 2:                 ████████████████
Request 3:                                 ████████████████
Skupaj: 1.5 s (nič bolje!)

### Asinhrono (FastAPI, s to_thread)

text

Request 1: ████████████████ (0.5 s) – v niti
Request 2: ████████████████ (0.5 s) – v niti
Request 3: ████████████████ (0.5 s) – v niti
Skupaj: 0.5 s (3× hitreje!)

## 💡 Zakaj to pomeni za tvojo kodo

### `/api/latest`

python

# 1. Redis – async, ker je redis.asyncio
latest_data = await redis_client.get("latest_merged_data")
# 2. update_data() – SINHRONA, zato to_thread
if latest_data is None:
    await asyncio.to_thread(update_data)   # ← ločena nit
# 3. Baza – async, ker je AsyncSession
payload = await _build_latest_from_db(db)

### `/api/history`

python

# 1. Redis – async
cached = await redis_client.get(f"history_payload:{period}")
# 2. Baza – async
payload = await build_history_payload_from_db_async(db, period)

**Vsi `await` so na async funkcijah** (Redis async, DB async). **`to_thread` je samo za `update_data()`**, ker je **sinhrona**.

## 🔍 Kaj je `asyncio` (kot modul)

**`asyncio` je Pythonov vgrajeni modul za async programiranje.** Vsebuje:

|Funkcija|Kaj dela|
|---|---|
|`asyncio.to_thread(fn)`|Požene **sinhrono** funkcijo v ločeni niti|
|`asyncio.sleep(s)`|Async spanje (ne blokira event loop)|
|`asyncio.gather(*tasks)`|Požene **več async funkcij hkrati**|
|`asyncio.create_task(coro)`|Ustvari "task" (async nalogo v ozadju)|

**Primer `asyncio.gather` – dve stvari hkrati:**

python

# Brez gather – zaporedno (1 s + 1 s = 2 s)
data1 = await fetch_from_api1()   # 1 s
data2 = await fetch_from_api2()   # 1 s
# Z gather – vzporedno (max(1 s, 1 s) = 1 s)
data1, data2 = await asyncio.gather(
    fetch_from_api1(),
    fetch_from_api2(),
)

## 📋 Povzetek

|Pojem|Kaj je|Primer|
|---|---|---|
|**`async def`**|Funkcija, ki lahko uporablja `await`|`async def get_latest():`|
|**`await`**|"Čakaj na rezultat, ampak medtem delaj drugo"|`await redis_client.get()`|
|**Event loop**|"Prometni policist" – usmerja requestе|En sam, teče v ozadju|
|**`asyncio.to_thread`**|Požene **sinhrono** funkcijo v ločeni niti|`await asyncio.to_thread(update_data)`|
|**`asyncio`**|Pythonov modul za async|`import asyncio`|
|**`asyncio.gather`**|Več async funkcij **vzporedno**|`await asyncio.gather(a(), b())`|

## 🎯 Ključno

**`asyncio` ni "async input output"** – je **"async I/O"** v smislu **čakanja na mrežo/disk/bazo**. Ideja je: **medtem ko ena funkcija čaka na odgovor, procesor dela drugo**.

**`await` je "ne blokiraj, medtem delaj drugo".**  
**`asyncio.to_thread` je "poženi sinhrono funkcijo v ločeni niti, da ne blokiraš event loopa".**

**Zakaj to rabiš:** Ker `update_data()` uporablja **sinhrone** knjižnice (`requests`, `SessionLocal`, sinhroni Redis). Če jih pokličeš neposredno v `async def`, **blokiraš event loop** in **vsi requesti čakajo**. Z `to_thread` jih poženeš v **ločeni niti** – event loop ostane prost.

---

**Zdaj:** če želiš, nadaljujeva s Fazo 2 (`/api/latest` router). Ampak **razumeš zdaj, zakaj je `to_thread` v kodi** – ne zato, ker bi bil "boljši", ampak zato, ker **brez njega bi `/api/latest` blokiral `/api/history`**.

nisem mislil input output userja in tipkovnice razumel, vau to je pravi čudež, to lahko kombiniraš da je veselje. Kdaj uporabiš ša async task?

Uporabnik je navdušen nad async/await in sprašuje, kdaj uporabiti `asyncio.create_task`. To je vprašanje o Python async programiranju, specifično o razliki med `await` in `create_task`. Odgovoriti moram v slovenščini, tehnično natančno, a razumljivo. Ker gre za konceptualno vprašanje programiranja, ni potrebe po iskanju po spletu. Odgovoril bom neposredno z razlago in primeri.

# 🎯 Kdaj uporabiti `asyncio.create_task` (in kdaj ne)

`await` in `create_task` sta si podobna, a imata **bistveno razliko**: `await` **čaka**, `create_task` **ne čaka** – požene nalogo v ozadju in gre takoj naprej.

## 🔍 Razlika v enem stavku

|Pristop|Kaj naredi|Kdaj nadaljuje|
|---|---|---|
|**`await coro()`**|Požene in **čaka**, da konča|Šele ko je končano|
|**`asyncio.create_task(coro())`**|Požene in **ne čaka** – gre naprej|Takoj, ko se task ustvari|

## 🎯 Kdaj uporabiti `create_task`

### 1. **"Fire and forget" – naloga, ki je ne rabiš takoj**

python

# Primer: logging v ozadju
async def log_request(path: str):
    await asyncio.sleep(0.1)  # simulacija počasnega loga
    logger.info(f"Request: {path}")
@router.get("/latest")
async def get_latest():
    asyncio.create_task(log_request("/latest"))  # ← ne čaka
    return {"data": "..."}  # ← vrne takoj

**Zakaj:** Log ni kritičen za odgovor. Stranka dobi podatke takoj, log se zapiše v ozadju.

### 2. **Vzporedno delo – več stvari hkrati**

python

# Primer: dva neodvisna fetcha
async def fetch_arso():
    await asyncio.sleep(0.5)
    return "arso_data"
async def fetch_docs():
    await asyncio.sleep(0.5)
    return "docs_data"
@router.get("/both")
async def get_both():
    task1 = asyncio.create_task(fetch_arso())   # ← požene
    task2 = asyncio.create_task(fetch_docs())   # ← požene
    # Oba tečeta VZPOREDNO
    result1 = await task1   # ← čaka na prvega
    result2 = await task2   # ← čaka na drugega
    return {"arso": result1, "docs": result2}

**Zakaj:** Brez `create_task` bi bila fetcha **zaporedna** (0.5 + 0.5 = 1 s). S `create_task` sta **vzporedna** (max(0.5, 0.5) = 0.5 s).

### 3. **Timeout – naloga, ki jo lahko prekineš**

python

# Primer: poženi, ampak ne čakaj več kot 2 s
async def slow_operation():
    await asyncio.sleep(10)  # zelo počasno
    return "done"
@router.get("/with-timeout")
async def get_with_timeout():
    task = asyncio.create_task(slow_operation())
    try:
        result = await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()  # ← prekini, če je prepočasno
        return {"error": "timeout"}
    return {"result": result}

**Zakaj:** Če naloga visi, jo lahko **prekineš** – `await` te možnosti ne da.

### 4. **Periodično opravilo – scheduler v ozadju**

python

# Primer: vsakih 10 s preveri, ali so novi podatki
async def poll_arso():
    while True:
        await update_data()
        await asyncio.sleep(10)
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poll_arso())  # ← požene v ozadju
    yield
    task.cancel()  # ← ustavi ob shutdownu

**Zakaj:** To je **background task** – teče, dokler app ne ugasne. `await` bi blokiral.

## ⚠️ Kdaj **ne** uporabiti `create_task`

|Situacija|Zakaj ne|
|---|---|
|**Potrebuješ rezultat za odgovor**|Uporabi `await` – `create_task` ne vrne rezultata takoj|
|**Naloga je kritična**|Če task faila, `create_task` tega ne pove – `await` vrne izjemo|
|**Naloga je kratka**|`create_task` ima overhead – za 1 ms nalogo je `await` boljši|
|**Nimaš reference na task**|Task lahko "pobegne" – vedno shrani `task = create_task(...)`, da ga lahko prekineš|

## 🛠️ Kaj pogosto zgrešimo – `create_task` ne vrne rezultata

python

# NAROBE – result je Task objekt, ne rezultat
result = asyncio.create_task(fetch_arso())
print(result)  # <Task pending name='...'>
# PRAVILNO – počakaj na rezultat
task = asyncio.create_task(fetch_arso())
result = await task  # ← zdaj dobiš rezultat

**`create_task` vrne `Task` objekt** – ne rezultata. Rezultat dobiš šele z `await task`.

## 📊 Primerjava – `await` vs `create_task` vs `gather`

|Pristop|Kaj naredi|Kdaj uporabi|
|---|---|---|
|**`await coro()`**|Požene, čaka|Ena naloga, rabiš rezultat|
|**`create_task(coro())`**|Požene, ne čaka|Več nalog vzporedno, ali background|
|**`await asyncio.gather(a(), b())`**|Požene **vse**, čaka **na vse**|Več nalog vzporedno, rabiš **vse** rezultate|

**`gather` je pogosto boljši od `create_task`**, ko rabiš več rezultatov:

python

# create_task – ročno
task1 = asyncio.create_task(fetch_arso())
task2 = asyncio.create_task(fetch_docs())
r1 = await task1
r2 = await task2
# gather – enako, ampak krajše
r1, r2 = await asyncio.gather(fetch_arso(), fetch_docs())

## 💡 Kdaj v **tvojem** projektu

|Situacija|Kaj uporabi|
|---|---|
|**`/api/latest` – Redis → DB**|`await` – rabiš rezultat za odgovor|
|**`/api/latest` – `update_data()`**|`await asyncio.to_thread(...)` – sinhrona funkcija|
|**`/api/history` – Redis → DB**|`await` – rabiš rezultat|
|**Background scheduler** (v Fazi 5)|`asyncio.create_task(scheduler_loop())` – teče v ozadju|
|**Logging, metrike**|`asyncio.create_task(log(...))` – ne čaka|

**V tvoji kodi zdaj `create_task` ne rabiš** – ker vsi endpointi čakajo na rezultat (`await`). `create_task` pride v poštev v **Fazi 5** – ko boš migriral scheduler v FastAPI `lifespan`.

## 📋 Povzetek

|Vprašanje|Odgovor|
|---|---|
|**Kaj je `create_task`?**|✅ Požene async funkcijo **v ozadju**, ne čaka|
|**Kdaj uporabiti?**|✅ Background naloge, vzporedno delo, timeout, periodična opravila|
|**Kdaj ne?**|❌ Ko rabiš rezultat takoj – takrat `await`|
|**Kaj vrne?**|✅ `Task` objekt – rezultat dobiš z `await task`|
|**Kaj je bolje od `create_task`?**|✅ `asyncio.gather` – ko rabiš **vse** rezultate|
|**Kje v tvojem projektu?**|⏳ Faza 5 – scheduler v `lifespan`|

---

**Ključno:** `create_task` je za **"poženi in pozabi"** – ko naloga ni kritična za odgovor, ali ko želiš **vzporedno** delo. V tvoji kodi zdaj `create_task` ne rabiš – vsi endpointi čakajo na rezultat. Pride v poštev v **Fazi 5** – ko boš migriral `BackgroundScheduler` v FastAPI `lifespan`.