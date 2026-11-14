

**Pred vsako večjo spremembo** (migracija, popravek nedoslednosti) naredi backup:

bash

docker exec airquality_postgres pg_dump -U airquality_user -d postgres > /opt/air_pollution_app/backup_$(date +%Y%m%d_%H%M%S).sql

**Preveri, da je backup uspel:**

bash

ls -lh /opt/air_pollution_app/backup_*.sql
head -5 /opt/air_pollution_app/backup_*.sql

**Če želiš obnoviti:**

bash

docker exec -i airquality_postgres psql -U airquality_user -d postgres < /opt/air_pollution_app/backup_20261026.sql

⚠️ **Pozor:** Obnova **prepiše** obstoječe podatke. Pred obnovo naredi še en backup trenutnega stanja.

---

## 3. Postopek: popravek nedoslednosti (2-urni zamik starih meritev)

**Kdaj:** Samo če želiš popraviti meritve, ki so bile shranjene med obdobjem, ko je container tekel v UTC (od premika do dodatka `TZ`).

**Koraki:**

### 3.1. Backup

bash

docker exec airquality_postgres pg_dump -U airquality_user -d postgres > /opt/air_pollution_app/backup_pred_popravkom_$(date +%Y%m%d_%H%M%S).sql

### 3.2. Ugotovi, katere meritve so napačne

bash

docker exec airquality_postgres psql -U airquality_user -d postgres -c "
SELECT COUNT(*) FROM measurements WHERE measured_at > NOW();"

**Če vrne majhno število** (npr. nekaj ur), so napačne samo tiste v prihodnosti. **Če vrne veliko**, je problem starejši.

### 3.3. Popravi samo meritve v prihodnosti

bash

docker exec airquality_postgres psql -U airquality_user -d postgres -c "
UPDATE measurements SET measured_at = measured_at - INTERVAL '2 hours' WHERE measured_at > NOW();"

**Kaj to naredi:** Odšteje 2 uri od vseh meritev, ki so **v prihodnosti** (torej napačno shranjene). Meritve v preteklosti ostanejo nedotaknjene.

### 3.4. Preveri, da je popravek uspel

bash

docker exec airquality_postgres psql -U airquality_user -d postgres -c "
SELECT MAX(measured_at), NOW() FROM measurements;"

**Pričakovano:** `MAX(measured_at)` ≤ `NOW()` (ne več v prihodnosti).

### 3.5. Počisti Redis cache

bash

docker exec air_pollution_app__redis redis-cli DEL history_payload:day history_payload:week history_payload:month history_payload:year

Nato znova poženi `update_data()` z `app.app_context()`, da se cache osveži.

---

## 4. Postopek: migracija v `timestamptz` (priporočeno za prihodnost)

**Kdaj:** Ko želiš, da so meritve **neodvisne od `TZ`** in da `MAX(measured_at) < NOW()` vedno drži.

### 4.1. Backup

bash

docker exec airquality_postgres pg_dump -U airquality_user -d postgres > /opt/air_pollution_app/backup_pred_migracijo_$(date +%Y%m%d_%H%M%S).sql

### 4.2. Migracija stolpca

bash

docker exec airquality_postgres psql -U airquality_user -d postgres -c "
ALTER TABLE measurements 
ALTER COLUMN measured_at TYPE timestamptz 
USING measured_at AT TIME ZONE 'Europe/Ljubljana';"

**Kaj to naredi:** Vsak naiven timestamp interpretira kot **CEST** in ga pretvori v `timestamptz` (absolutni trenutek). Nato `MAX(measured_at)` ne bo več v prihodnosti, ne glede na `TZ` containerja.

### 4.3. Popravi model (SQLAlchemy)

V `backend/models/measurement.py` (ali kjer je model):

python

# Prej:
measured_at = Column(DateTime, nullable=False)
# Potem:
measured_at = Column(DateTime(timezone=True), nullable=False)

### 4.4. Popravi parser

V `backend/parsers/models/measurement_model.py`:

python

from zoneinfo import ZoneInfo
CEST = ZoneInfo("Europe/Ljubljana")
# Prej:
time_to = datetime.strptime(time_to_text, "%Y-%m-%d %H:%M")
# Potem:
time_to = datetime.strptime(time_to_text, "%Y-%m-%d %H:%M").replace(tzinfo=CEST)

### 4.5. Popravi poizvedbe

V `backend/utils/history_cache.py`:

python

from datetime import datetime, timezone
# Prej:
start_ts = _period_start(period)  # naiven
end_ts = datetime.now()  # naiven
# Potem:
start_ts = _period_start(period)
if start_ts.tzinfo is None:
    start_ts = start_ts.replace(tzinfo=timezone.utc)
end_ts = datetime.now(timezone.utc)

### 4.6. Preveri

bash

docker exec airquality_postgres psql -U airquality_user -d postgres -c "
SELECT MAX(measured_at), NOW() FROM measurements;"

**Pričakovano:** `MAX(measured_at) < NOW()` (vedno, ne glede na `TZ`).

---

## 5. Povzetek v eni tabeli

|Kaj|Ukaz|Kdaj|
|---|---|---|
|**Backup baze**|`pg_dump -U airquality_user -d postgres > backup.sql`|Pred vsako večjo spremembo|
|**Obnova baze**|`psql -U airquality_user -d postgres < backup.sql`|Če gre kaj narobe|
|**Popravek 2h zamika**|`UPDATE measurements SET measured_at = measured_at - INTERVAL '2 hours' WHERE measured_at > NOW();`|Samo za napačne meritve|
|**Migracija v `timestamptz`**|`ALTER TABLE ... TYPE timestamptz USING ... AT TIME ZONE 'Europe/Ljubljana';`|Za trajno rešitev|
|**Počisti Redis**|`redis-cli DEL history_payload:*`|Po popravku/migraciji|