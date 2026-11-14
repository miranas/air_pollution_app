Problem je bil:

1. **Parser je shranjeval naiven `datetime`** (`2026-10-21 20:00` brez `tzinfo`).
    
2. **Container je tekel v UTC**, meritve pa so bile v CEST.
    
3. **PostgreSQL je naiven timestamp interpretiral kot UTC** – zato so bile meritve 2 uri v prihodnosti.
    

**Rešitev:** `TZ=Europe/Ljubljana` je poskrbel, da sta container in meritve v **istem časovnem pasu**. To je pravilno.

Potem, ko sem kontainer premaknil v drugo mapo in ga zagnal, je poleg tega da je docker ustvaril za to kontejner ločeno omrežje, samodejno nastavil čas na UTC, ker v docker-compose ni bil eksplicitno nastavljen. 

**Simptom:** `/api/history?period=day` je vračal prazen `"stations": {}`, čeprav je baza imela 458.212 meritev. `MAX(measured_at)` je bil 40 minut **v prihodnosti** glede na `NOW()`.

**Vzrok:** Container je tekel v **UTC**, ARSO pa pošilja meritve v **lokalnem času (CEST, UTC+2)**. Parser je prebral `20:00` (lokalno) in shranil kot naiven `datetime`, PostgreSQL pa ga je interpretiral kot UTC. Zato so bile meritve 2 uri v prihodnosti, poizvedba `WHERE measured_at <= NOW()` pa jih ni zajela.

**Rešitev:**

1. V `docker-compose.yml` dodan `TZ=Europe/Ljubljana` v storitvi `backend` in `postgres`.
    
2. Containerja znova zagnana (`docker compose up -d`).
    
3. Preverjeno: `docker exec air_pollution_app date` → `CEST` ✅
    
4. Ročno pognan `update_data()` z `app.app_context()` (Flask kontekst), da se je `history_payload:*` zapisal v Redis.
    

**Posledica:** `/api/history` zdaj vrača podatke, animacija dela.

**Naučeno:**

- `timestamp without time zone` je krhka izbira – ob spremembi `TZ` se interpretacija spremeni.
    
- V `docker-compose.yml` vedno nastavi `TZ=Europe/Ljubljana` v vseh storitvah, ki delajo s čas
## 2-urni zamik v starih meritvah (oktober 2026)

**Simptom:** Meritve, shranjene med premikom `docker-compose.yml` (pred dodatkom `TZ`), imajo 2-urni zamik.

**Vzrok:** Container je tekel v UTC, meritve pa so bile v CEST.

**Rešitev:** `TZ=Europe/Ljubljana` v `docker-compose.yml` (že narejeno).

**Status:** Stare meritve imajo 2-urni zamik, ampak to je zanemarljivo za trende. **Ne popravljamo** – tveganje ni vredno.

**Kdaj popraviti:** Če bo kdaj treba (npr. za diplomo, kjer mora biti vse natančno), takrat narediti backup in migracijo v `timestamptz`.