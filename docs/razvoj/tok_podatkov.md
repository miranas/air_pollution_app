# Tok podatkov – air_pollution_app

> Zapisano: 2026-11-10
> Namen: eno mesto, kjer je opisan celoten tok od ARSO XML do grafa, vključno z
> mesti, kjer je tok robusten, in mesti, kjer tiho odpoveduje.
> Opomba: številke vrstic se med refaktorjem premikajo – išči po imenih funkcij.

---

## 1. Pregled

Aplikacija ima tri jasno ločene odgovornosti:

| sloj | datoteke | odgovornost |
|---|---|---|
| I/O in validacija | `backend/network/`, `backend/parsers/` | fetch XML, parse, merge, DB insert |
| analitika | `backend/analytics/` (`agregation.py`, `aqi.py`) | čiste funkcije: bucketing, downsampling, AQI |
| orkestracija | `backend/data/update_data.py`, `backend/utils/history_cache.py`, `backend/utils/redis.py` | kdaj brati/pisati DB in Redis |
| API | `backend/routes/api_latest.py` (Flask), `api_latest_fastapi.py` (FastAPI) | branje iz cachea, fallback |

Te meje so pravilne in jih ne gre združevati. Vsaka datoteka ima svojo pogodbo.

---

## 2. Diagram toka

```
                     ┌──────────────────────────────────┐
                     │ startup:  backend/app.py:118-120 │
                     │ scheduler: backend/app.py:99-114 │  vsako uro
                     └────────────────┬─────────────────┘
                                      ▼
                         update_data()   data/update_data.py:17
                                      │
   1. fetch_arso_xml()                │  network/arso_client.py
      → (ok, xml, error)              │
                                      ▼
   2. parse_stations_from_xml()       │  parsers/station_parser.py
      → ParseResult                   │
                                      ▼
   3. parse_measurements_from_xml()   │  parsers/measurments_parser.py
      → ParseResult                   │
                                      ▼
   4. merge_stations_and_measurements()   parsers/..._merger.py
      → {station_id: {info, measurements_list}}
                                      │
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
   5. Redis                      6. DB                    7. refresh_history_cache()
      'latest_merged_data'          measurements             utils/history_cache.py
      (utils/redis.py)              (parsers/insert_data.py)        │
                                                                    ▼
                                                     build_history_payload_from_db()
                                                     utils/history_cache.py
                                                        │ SQL (okno periode)
                                                        ▼
                                                     agregacija → downsample → AQI
                                                     analytics/agregation.py, aqi.py
                                                        ▼
                                                     Redis 'history_payload:{period}'
                                                     (4 ključi: day/week/month/year)


  REQUEST /api/history?period=year
      → get_history_payload()  utils/history_cache.py
          ├─ Redis hit  → vrni takoj
          └─ miss       → build iz DB → zapiši v Redis
```

---

## 3. Faza po fazi

### Faza 1 – fetch (`backend/network/arso_client.py`)

**Pogodba:** `(success: bool, xml: str | None, error: str | None)`.

- vir: `ARSO_STATIONS_URL` (`backend/network/config.py`) – XML z zadnjimi urnimi podatki,
- `timeout=REQUEST_TIMEOUT` (10 s),
- `response.encoding = "utf-8"`, `raise_for_status()`,
- `@handle_http_request_exception` pretvori `Timeout`, `ConnectionError` in
  `RequestException` v `(False, None, sporočilo)`.

**Popravljeno 2026-11-10:** `@handle_exceptions` odstranjen. Ta dekorator vrača
Flaskski `(jsonify(...), status)`, kar poruši 3-tuple pogodbo in v
`update_data()` povzroči `ValueError` pri razpakiranju. Prav tako je odstranjen
blanket `except Exception` iz `handle_http_request_exception` – nepredvidene
napake naj se vidijo, ne pa da se pretvorijo v "data error".

**Retry/backoff:** implementiran 2026-11-14 (3 poskusi, pavza 1 s / 2 s,
retry samo za prehodne napake – glej razdelek 7, Step 2).

### Faza 2 – parse (`parsers/station_parser.py`, `parsers/measurments_parser.py`)

**Pogodba:** `ParseResult(success, data, items_parsed, error_message)`.

Dobro:
- vsak element v `try/except` – ena slaba postaja ne podre celotnega XML,
- `ET.ParseError` in `UnicodeDecodeError` se obravnavata ločeno,
- validacija v `ParsedMeasurementModel.__post_init__`
  (`parsers/models/measurement_model.py`): `station_id`, ime, `time_from < time_to`.

Luknje:
1. `parse_measurements_from_xml` vrne `success=True`, tudi če so bili **vsi**
   elementi preskočeni (`data=[]`). "0 uspešno parsanih" bi moralo biti failure.
2. `_to_float` za vrednosti tipa `"<2"` naredi `float("<")` → `ValueError` →
   `None`, medtem ko `_to_int` isto vrednost pretvori v `2`. `co` in `benzen`
   (float polji) zato izgubita meritve pod mejo detekcije.
3. Čas: `datetime.strptime(..., "%Y-%m-%d %H:%M")` vrne **naive** datetime.
   ARSO piše lokalni slovenski čas (CET/CEST). Če aplikacija teče v Dockerju z
   UTC, so okna in bucketing zamaknjeni za 1–2 h (glej Step 4).

### Faza 3 – merge (`parsers/stations_and_measurments_merger.py`)

**Pogodba:** `dict[station_id] → {"info": ParsedStationModel, "measurements_list": [...]}`.

- postaje brez meritev ostanejo s praznim seznamom (pravilno),
- meritve brez pripadajoče postaje se logajo in **zavržejo** – če ARSO doda
  postajo samo v meritvah, se tiho izgubi,
- brez I/O, deterministično.

### Faza 4 – "latest" cache (`backend/utils/redis.py`)

**Pogodba:** zapiše `latest_merged_data` v Redis.

Vrstni red fallbackov:
1. Redis (`current_app.extensions['redis_client']`),
2. Flask SimpleCache (`CACHE_TYPE=SimpleCache`),
3. module-global `_LATEST_MERGED_DATA_JSON` (samo v procesu).

**Luknja (kritična):** v `update_data()` je cache write **pred** preverjanjem
praznosti (`update_data.py:41` vs `:47`). Če parse postaj spodleti, se v Redis
zapiše `{}` in povozi zadnji dobri snapshot; `/api/latest` nato vrne 503.

**Omejitev:** SimpleCache je per-process. Gunicorn je nastavljen na
`--workers 1` (`docker/Dockerfile`), zato je trenutno konsistenten. Ob
povečanju števila Python procesov bi vsak dobil svojo kopijo – takrat je
Redis obvezen, ne fallback.

### Faza 5 – DB insert (`backend/parsers/insert_data.py`)

- `ensure_pollutants_in_db()` → `ON CONFLICT (name) DO NOTHING`;
  `pollutants.name` ima `unique=True` (`database/db_models.py`),
- postaja: `ON CONFLICT (station_id) DO NOTHING`, nato `commit()` – postaja se
  commita **pred** meritvami,
- meritve: `ON CONFLICT (station_id, pollutant_id, measured_at) DO NOTHING`,
- outer `commit()` na koncu, per-station `rollback()` ob napaki.

Luknje:
1. Vse izjeme se požrejo in samo `print`ajo. `insert_all_data` ne vrne uspeha,
   zato `update_data` misli, da je uspelo, in osveži history **iz stare DB**.
2. `ON CONFLICT (station_id, pollutant_id, measured_at)` zahteva ustrezen
   unique index. V `db_models.py` ga ni – model in dejanska shema se razhajata.
   Preveri v bazi: `\d measurements`.
3. `print` namesto `logging.exception` – brez tracebacka in brez metrike.

### Faza 6 – precompute history (`backend/utils/history_cache.py`)

`refresh_history_cache()` za vsako periodo `day/week/month/year`:

1. `_period_start(period)` → okno 1 dan / 7 dni / 30 dni / 365 dni,
2. en SQL join `stations + measurements + pollutants`, filter po `measured_at`,
3. grupiranje po `station_id` in `measured_at.isoformat()`,
4. po postaji:
   - `_aggregate_measurements_by_period()` – združi v 1h/3h/6h/24h koše in **povpreči**,
   - `_downsample_measurements()` – trda zgornja meja točk (safety net),
   - `_attach_aqi_indices()` – doda `aqi_eu` in `aqi_who`,
5. `cache_history_payload()` → Redis `history_payload:{period}`, brez TTL.

To je "Redis, vključno z letnimi": letni payload se izračuna ob vsakem urnem
update-u in leži v Redisу. DB se bere tukaj, ne na request.

### Faza 7 – serving

- Flask `/api/history` (`routes/api_latest.py`): validacija periode, rate limit,
  `get_history_payload()`, `Cache-Control`.
- `get_history_payload()`: Redis → hit; miss → build iz DB → write-back.
- FastAPI `/history` (`routes/api_latest_fastapi.py`): bere isti Redis ključ;
  fallback kliče `build_history_payload_from_db_async`, ki **ne obstaja**.
  Med migracijo to pomeni, da FastAPI streže samo iz Redisа (normalno dovolj).

---

## 4. DB in Redis – zakaj oba

- **DB = source of truth.** ARSO XML vsebuje samo trenutni snapshot; zgodovina
  nastane z urnimi inserti. Redis je izgubljiv (v `docker/docker-compose.yml`
  nima volume-a ne persistence), DB pa omogoča rebuild in SQL statistiko.
- **Redis = materializirani pogled (cache).** Bere se na request; piše ob
  urnem update-u. Cache-aside vzorec je pravilen.
- Gradnja iz DB **na request** je rezerva, ne normalna pot. Če se pogosto
  dogaja, je nekaj narobe s polnjenjem cachea (npr. `NameError` v
  `refresh_history_cache`, nedosegljiv Redis, prazen Redis po restartu).

Hitro preverjanje:

```bash
redis-cli KEYS 'history_payload:*'
redis-cli STRLEN history_payload:year
```

V logu:

```
Refreshed history cache for all periods          ← OK
Failed to refresh history cache for period=...    ← napaka
Cache: Redis ni dostopen, uporabljam SimpleCache  ← Redis ni dosegljiv
```

---

## 5. Agregacija, downsample in AQI

### Bucket velikosti (`analytics/agregation.py`)

| period | bucket | košev v obdobju | `MAX_POINTS_BY_PERIOD` |
|---|---|---|---|
| day | 1 h | 25 (24 h + rob) | 25 |
| week | 3 h | 57 | 57 |
| month | 6 h | 121 | 121 |
| year | 24 h | 366 | 366 |

Vrednosti so nastavljene na "košev + 1", da je downsample res samo varovalka.
Ker agregacija vrne največ toliko košev, se `_downsample_measurements` v
normalnem delovanju ne sproži (razen ob DST robovih).

### Kaj agregacija naredi

`row[pollutant_key] = round(total / count, 2)` – **povprečje** vrednosti v košu.

### Zakaj je to vsebinsko pomembno

Povprečenje izniči vrhove:

| ura | PM10 |
|---|---|
| 23 ur | 20 µg/m³ |
| 1 ura | **150 µg/m³** |

Dnevno povprečje = `(23·20 + 150) / 24 ≈ 25,4` → vrh izgine. Pri mesecu
(6-urni koši) se raztopi še bolj.

Dodatno: `_attach_aqi_indices` teče **po** agregaciji, torej je AQI izračunan
iz povprečja, ne iz najslabše ure.

**Posledica:** "kolikokrat je bila vrednost presežena" iz tega payloada ni
mogoče izračunati. Za to je potrebna ločena statistika nad surovimi vrstami
(glej razdelek 8).

### Downsample

```python
sampled = measurements[::step]
if sampled[-1] != measurements[-1]:
    sampled = sampled[:max_points - 1] + [measurements[-1]]
else:
    sampled = sampled[:max_points]
```

- `step = len // max_points` ne garantira dolžine, zato je rez na koncu nujen.
- `else` veja ob `len == max_points + 1` odreže **zadnji** element, kar je v
  nasprotju z docstringom. S trenutnimi mejami (košev + 1) se to v praksi ne
  zgodi, a popravek je trivialen: vedno
  `sampled[:max_points - 1] + [measurements[-1]]`.

---

## 6. Robustnostne luknje (prioriteta)

| # | mesto | težava | posledica |
|---|---|---|---|
| 1 | `update_data.py:41` | cache write pred preverjanjem praznosti | prazni `latest_merged_data` |
| 2 | `update_data.py:27` | `station_result.success` se ne preveri | izguba vseh meritev, tiho |
| 3 | `insert_data.py` | izjeme se požrejo + `print` | history iz stare DB, brez tracebacka |
| 4 | `db_models.py` | ni unique indexa za `ON CONFLICT` | insert lahko pade |
| 5 | `measurement_model.py` | `"<2"` pri float poljih → `None` | izguba `co`, `benzen` |
| 6 | povsod | naive datetimes + Docker UTC | okna zamaknjena 1–2 h |
| 7 | `history_cache.py` | ni `build_history_payload_from_db_async` | FastAPI fallback ne dela |
| 8 | `measurments_parser.py` | `success=True` pri 0 parsanih | "uspeh" z praznimi podatki |

---

## 7. Načrt popravkov

| Step | status | kratek opis |
|---|---|---|
| 1 | ✅ narejeno | dekoratorji v data sloju |
| 2 | ⏳ predlog | retry v `arso_client.py` |
| 3 | ☐ | vrstni red in napake v `update_data()` |
| 4 | ☐ | časovni pas |
| 5 | ☐ | unique index za meritve |
| 6 | ☐ | statistika prekoračitev |

### Step 1 – dekoratorji ✅ (2026-11-10)

- `@handle_exceptions` odstranjen iz `fetch_arso_xml` in `parse_stations_from_xml`.
- `handle_exceptions` dobil opozorilo: samo za Flask route handlerje.
- Odstranjen blanket `except Exception` iz `handle_http_request_exception`;
  popravljena f-string napaka v `handle_service_exception`.
- Preverjeno: `compile OK`, 22 testov, `build_history_payload_from_db('day')`
  vrne 23 postaj.

### Step 2 – retry v `arso_client.py` ✅ (implementirano 2026-11-14)

#### Prejšnje stanje (po Step 1, pred retryjem)

```python
@handle_http_request_exception
@add_timing
def fetch_arso_xml() -> Tuple[bool, Optional[str], Optional[str]]:
    logging.info(f"Fetching ARSO xml data from {ARSO_STATIONS_URL}")

    response = requests.get(ARSO_STATIONS_URL, timeout=REQUEST_TIMEOUT)
    response.encoding = 'utf-8'
    response.raise_for_status()

    logging.info(f"Successfully fetched ARSO xml data Length: {len(response.text)} characters")
    return True, response.text, None
```

En poskus na uro. Ob timeoutu, prenosni napaki ali 5xx se je ura izgubila –
podatek za to uro ni prišel nikoli, ker naslednji fetch prinese samo novejši
snapshot.

#### Politika

| parameter | vrednost |
|---|---|
| poskusi | 3 (1 + 2 ponovitvi) |
| backoff | 1 s, 2 s |
| retry | `Timeout`, `ConnectionError`, HTTP 429/500/502/503/504 |
| brez retry | ostali 4xx |
| timeout | `(3.05 connect, 10 read)` |

Osnutek:

```python
import time

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _is_retryable(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    return response is not None and response.status_code in RETRYABLE_STATUS_CODES


def _fetch_once() -> str:
    response = requests.get(
        ARSO_STATIONS_URL,
        timeout=(3.05, REQUEST_TIMEOUT),
    )
    response.encoding = "utf-8"
    response.raise_for_status()
    return response.text


@add_timing
def fetch_arso_xml() -> Tuple[bool, Optional[str], Optional[str]]:
    last_error = "unknown error"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            logging.info("Fetching ARSO XML (attempt %d/%d)", attempt, MAX_ATTEMPTS)
            xml_text = _fetch_once()
            logging.info("Fetched ARSO XML: %d characters", len(xml_text))
            return True, xml_text, None
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt >= MAX_ATTEMPTS or not _is_retryable(exc):
                break
            delay = BACKOFF_SECONDS[attempt - 1]
            logging.warning(
                "ARSO fetch failed (attempt %d/%d): %s; retrying in %.1fs",
                attempt, MAX_ATTEMPTS, exc, delay,
            )
            time.sleep(delay)

    logging.error("ARSO fetch failed after %d attempt(s): %s", attempt, last_error)
    return False, None, f"ARSO fetch failed after {attempt} attempt(s): {last_error}"
```

Ob tem odstranimo `@handle_http_request_exception` s `fetch_arso_xml` (zanka
pokrije vse `RequestException`).

#### Razlaga predloga

- **`_fetch_once()`** – en sam poskus. Ločen je zato, da je zanka čitljiva in
  da lahko testiraš eno stvar naenkrat. Vrne `str` ali dvigne
  `requests.RequestException`.
- **`timeout=(3.05, REQUEST_TIMEOUT)`** – tuple pomeni `(connect, read)`.
  Connect 3.05 s hitro odpove, če ARSO ni dosegljiv; read ostane 10 s kot zdaj.
  (3.05 je uveljavljena vrednost: 3 s + majhen margin.)
- **`_is_retryable()`** – odloča, ali ima smisel ponavljati:
  - `Timeout` in `ConnectionError` so prehodne narave → retry,
  - HTTP 429 (rate limit) in 5xx → retry,
  - ostali 4xx (403, 404) → **ne** ponavljaj, ker se ne bodo popravili.
  `raise_for_status()` dvigne `HTTPError`, ki ima `.response`, zato status
  preberemo od tam.
- **`MAX_ATTEMPTS = 3`** – 1 poskus + 2 ponovitvi. Več nima smisla, ker
  scheduler itak poskusi spet čez eno uro.
- **`BACKOFF_SECONDS = (1.0, 2.0)`** – spanec med poskusi; brez tega bi trije
  poskusi udarili v isti sekundi in verjetno dobili isto napako.
- **`break`** – izstop, ko napaka ni retryable ali so poskusi porabljeni.
  `attempt` ostane definiran tudi po zanki, zato ga uporabimo v sporočilu.
- **Pogodba se ne spremeni** – funkcija še vedno vrača
  `(bool, xml|None, error|None)`, zato `update_data()` ostane nespremenjen.
- **Zakaj eksplicitna zanka in ne `HTTPAdapter` + `Retry`** – retry v urllib3
  je skrit; težje logiraš vsak poskus, težje testiraš z `monkeypatch` in težje
  izključiš 4xx. Zanka je nekaj vrstic več, a je celoten tok viden na enem
  mestu.

Najslabši možni čas: `3 × (3.05 + 10) + 1 + 2 ≈ 42 s`. Teče v background
threadu schedulerja, zato ne blokira requestov.

#### Test

```python
import requests


class FakeResponse:
    text = "<xml/>"
    encoding = "utf-8"

    def raise_for_status(self):
        pass


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.Timeout("boom")
        return FakeResponse()

    monkeypatch.setattr("backend.network.arso_client.requests.get", fake_get)
    monkeypatch.setattr("backend.network.arso_client.time.sleep", lambda _: None)

    ok, xml, err = fetch_arso_xml()
    assert ok is True
    assert xml == "<xml/>"
    assert err is None
    assert calls["n"] == 3


def test_does_not_retry_4xx(monkeypatch):
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        response = requests.Response()
        response.status_code = 404
        raise requests.HTTPError(response=response)

    monkeypatch.setattr("backend.network.arso_client.requests.get", fake_get)
    monkeypatch.setattr("backend.network.arso_client.time.sleep", lambda _: None)

    ok, xml, err = fetch_arso_xml()
    assert ok is False
    assert xml is None
    assert calls["n"] == 1
```

### Step 3 – `update_data()` vrstni red in napake

1. preveri `station_result.success` in `measurement_result.success`,
2. preveri `merged_data` **pred** cache write,
3. `insert_all_data` naj vrne `bool` (ali dvigne),
4. history refresh samo, če je DB insert uspel.

### Step 4 – časovni pas ✅ (odločeno 2026-11-16)

**Odločitev:** shranjujemo aware UTC, v lokalni čas pretvarjamo samo na meji prikaza.

- V bazi bo `measured_at` tipa `timestamptz` (Faza 3) in bo edini vir resnice.
- Parser prebere lokalni čas ARSO (`Europe/Ljubljana`) in ga takoj pretvori v UTC:
  `datetime.strptime(...).replace(tzinfo=ZoneInfo("Europe/Ljubljana")).astimezone(timezone.utc)`.
- Vse poizvedbe primerjajo aware UTC: `datetime.now(timezone.utc)`.
- API vrne ISO 8601 z offsetom (`+00:00`); pretvorba v `Europe/Ljubljana` se zgodi
  na prikazu (frontend).
- `TZ=Europe/Ljubljana` v containerjih ostane kot varnostna mreža za knjižnice,
  ki uporabljajo sistemski čas. To **ni** mehanizem pravilnosti.

**Zakaj:** prehod CEST/CET (zadnja nedelja v marcu in oktobru) naredi naivne
čase dvoumne. Aware UTC je vedno enoličen, zato so primerjave, vrstni red in
okna pravilni ne glede na strežnik.

**Vmesno stanje (do Faze 3):** koda še uporablja naivne `datetime.now()` in
`DateTime` brez timezone. Zato so okna in bucketing zamaknjeni za 1–2 h
(glej razdelek 3.3). Migracija v Fazi 3 to odpravi skupaj s TimescaleDB.

**TimescaleDB:** hypertable ne spremeni tipa stolpca sam.
`ALTER ... TYPE timestamptz USING measured_at AT TIME ZONE 'Europe/Ljubljana'`
ostaja obvezen korak. `time_bucket(..., 'Europe/Ljubljana')` se uporabi le tam,
kjer so bucketi vezani na lokalni dan.

### Step 5 – unique index

Preveri `\d measurements` in po potrebi dodaj
`UniqueConstraint('station_id', 'pollutant_id', 'measured_at')` v model.

### Step 6 – statistika prekoračitev (ločeno od grafa)

Graf ostane povprečen, statistika pa gre iz surovih vrst:

```sql
SELECT pollutant_id,
       COUNT(*) FILTER (WHERE value > :limit) AS exceed_count,
       MAX(value) AS max_value,
       AVG(value) AS mean_value
FROM measurements
WHERE measured_at >= :start
GROUP BY pollutant_id;
```

Mejne vrednosti za to niso `AQI_THRESHOLDS_EU/WHO` (to so meje AQI pasov),
ampak zakonske meje z ustreznim povprečnim obdobjem iz
`ai/rag_sources/mejne_vrednosti.txt` in
`ai/rag_sources/zakonodaja_in_mejne_vrednosti.txt`.

---

## 8. Kako debugirati tok

Najprej mora biti odprt SSH tunel na Hetzner, ker `.env` kaže na
`127.0.0.1:5432` in `127.0.0.1:6379`:

```bash
./ssh_tunel.sh

nc -z 127.0.0.1 5432 && echo "DB OK"
nc -z 127.0.0.1 6379 && echo "Redis OK"
```

### A. Samo čiste funkcije (brez DB/Redis)

```python
from backend.analytics.agregation import _aggregate_measurements_by_period
from backend.analytics.aqi import _attach_aqi_indices

rows = [
    {"station_id": "E403", "time_to": "2026-11-09T23:00:00", "pm10": 20.0},
    {"station_id": "E403", "time_to": "2026-11-09T22:00:00", "pm10": 150.0},
]
agg = _aggregate_measurements_by_period(rows, "day")
print(_attach_aqi_indices(agg))
```

### B. Prava baza

```python
from backend.app import create_app

app = create_app(start_scheduler=False, run_initial_update=False)
with app.app_context():
    from backend.utils.history_cache import build_history_payload_from_db
    payload = build_history_payload_from_db("day")
    station = next(iter(payload["stations"].values()))
    print(len(station["measurements_list"]), station["measurements_list"][:2])
```

### C. Breakpointi

| mesto | kaj pogledaš |
|---|---|
| `update_data.py` fetch/parse/merge | ali je rezultat neprazen in `success=True` |
| `history_cache.py` pred agregacijo | `raw_measurements` |
| `agregation.py` pri `total / count` | kako nastane povprečje |
| `history_cache.py` po `_attach_aqi_indices` | AQI iz povprečja |
| `get_history_payload()` | ali je bil Redis hit ali DB fallback |

---

## 9. Okolje

- `.env` (lokalno): `DB_HOST=127.0.0.1`, `DB_PORT=5432`,
  `REDIS_URL=redis://127.0.0.1:6379` – oboje gre skozi `ssh_tunel.sh`.
- Docker: `REDIS_URL` je v compose override-an na `redis://redis:6379`;
  `DB_HOST` pride iz `.env` – v containerju `127.0.0.1` ne kaže na `postgres`
  service, zato mora produkcijski `.env` imeti pravo vrednost.
- Gunicorn: `--workers 1` (`docker/Dockerfile`) – en proces, en scheduler,
  en SimpleCache. Nginx `worker_processes auto` so ločeni procesi in ne
  vplivajo na Python cache/scheduler.

---

## 10. Dnevnik sprememb

| datum | korak | kaj | preveritev |
|---|---|---|---|
| 2026-11-10 | Step 1 | Odstranjen `@handle_exceptions` iz `fetch_arso_xml` in `parse_stations_from_xml`; opozorilo v docstringu; zožen `handle_http_request_exception`; popravljena f-string v `handle_service_exception` | `compile OK`, 22/22 testov, `build_history_payload_from_db('day')` → 23 postaj |
| 2026-11-10 | Step 2 | Zapisana politika, osnutek kode, razlaga in testi za retry | čaka implementacijo |
| 2026-11-14 | Step 2 | Implementiran retry v `fetch_arso_xml`: 3 poskusi, backoff 1 s/2 s, retry za `Timeout`, `ConnectionError`, 429 in 5xx; `@handle_http_request_exception` odstranjen (zanka vrača tuple sama); dodani 4 testi | 38/38 testov |
| 2026-11-16 | Step 4 | Zapisana odločitev: aware UTC v `timestamptz`, pretvorba v `Europe/Ljubljana` samo na prikazu; `TZ` v containerju ostane varnostna mreža; TimescaleDB ne odpravi `ALTER` koraka | dokument posodobljen |
