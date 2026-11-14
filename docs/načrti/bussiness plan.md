## 1. Načelo – **vzporedna tira, ne "ali–ali"**

|Tir|Dnevni čas|Kdaj|
|---|---|---|
|**Tehnični**|2,5–3 h|Zjutraj / dopoldne|
|**Poslovni**|1–1,5 h|Popoldne|
|**Skupaj**|**4 h/dan**|–|

**Zakaj vzporedno:** Če čakaš, da "končaš tehnično", boš izgubil **tedne** brez dohodka. Poslovni tir **ne rabi** končanega projekta – rabi **portfolio stran + predloge**.

---

## 2. Tehnični tir – **3 faze**

### Faza A: Zaključi `tok_podatkov.md` popravke (3–4 dni)

| Dan   | Kaj                                                                               | Čas    |
| ----- | --------------------------------------------------------------------------------- | ------ |
| **1** | **Step 3** – `update_data.py` (3.1, 3.2) + `insert_data.py` (refaktor, `-> bool`) | 2,5 h  |
| **1** | **Testi** – `pytest` 26 passed                                                    | 15 min |
| **2** | **Step 2** – retry v `arso_client.py` + testa                                     | 1 h    |
| **2** | **Step 4** – dokumentiraj `TZ` v `tok_podatkov.md`                                | 15 min |
| **3** | **Faza 2.2** – split `build_history_payload_from_db`                              | 1,5 h  |
| **3** | **Testi** – 26 passed                                                             | 15 min |
| **4** | **Faza 2.3** – async fallback                                                     | 1,5 h  |
| **4** | **Testi + `curl`**                                                                | 30 min |

**Rezultat:** **`tok_podatkov.md` popravki zaključeni.** Backend **production ready**.

### Faza B: Zaključi 6-fazni plan (3–4 dni)

|Dan|Kaj|Čas|
|---|---|---|
|**5**|**Faza 3** – `timestamptz` migracija (backup → ALTER → model/parser)|2 h|
|**5**|**Faza 4** – async testi (10–15 testov)|1 h|
|**6**|**Faza 5a** – scheduler v FastAPI `lifespan`|1 h|
|**6**|**Faza 5b** – Prometheus, `after_request`, `/api/status`|1 h|
|**7**|**Faza 5c** – SSL + domena|1 h|
|**7**|**Faza 5d** – Docker (`gunicorn` → `uvicorn`)|30 min|
|**8**|**Faza 5e** – `app.py` → `legacy/`|15 min|
|**8**|**Agent endpoint** `/api/ask`|30 min|

**Rezultat:** **FastAPI 100 %**, **produkcija živa**, **agent dostopen prek HTTP**.

### Faza C: Frontend + Arduino (2–3 tedni, vzporedno s poslovnim)

|Teden|Kaj|Čas/dan|
|---|---|---|
|**Teden 3**|Frontend – **mapa Slovenije** (Leaflet) + markerji|2 h|
|**Teden 3**|Frontend – **history chart** (Recharts)|1 h|
|**Teden 4**|Frontend – **agent chat UI**|1,5 h|
|**Teden 4**|**Arduino naročilo** (ko bo denar)|1 dan|
|**Teden 5–6**|Arduino – **sestavljanje, testiranje, kalibracija**|2 h|

**Rezultat:** **Polni produkt** – mapa, grafi, agent, senzorji.

---

## 3. Poslovni tir – **od dneva 1**

### Teden 1: **Portfolio + Upwork** (1 h/dan)

|Dan|Kaj|Čas|
|---|---|---|
|**1**|**Portfolio stran** – GitHub Pages, 1 stran|30 min|
|**2**|**Portfolio stran** – opisi projektov, archflow, `tok_podatkov.md`|30 min|
|**3**|**Upwork profil** – naslov, opis, portfolio|30 min|
|**3**|**Freelancermap profil** – DACH trg|30 min|
|**4**|**5 predlogov** – prvi dan|30 min|
|**5–7**|**5 predlogov/dan** + LinkedIn objava|30 min/dan|

**Rezultat:** **Portfolio živi + profili + prvi predlogi.**

### Teden 2–3: **Aktivna prodaja** (1 h/dan)

|Kaj|Kdaj|
|---|---|
|**5 predlogov/dan** na Upwork + Freelancermap|Vsak dan 30 min|
|**LinkedIn objave** (3× teden)|15 min|
|**Klici lokalnih podjetij** (10 klicev)|2× teden 30 min|
|**Plesni večeri** (mreža)|1–2× teden|

**Rezultat:** **1–2 razgovora** s strankami.

### Teden 4–7: **Prvi posel + razpisi** (1,5 h/dan)

|Kaj|Kdaj|
|---|---|
|**5 predlogov/dan**|Vsak dan 30 min|
|**Prvi majhen posel** (100–500 €)|Ko pride|
|**Interreg partnerji** – e-pošta (Nova Gorica, Gorizia, UNG)|2 h/teden|
|**P2/ARIS razpisi** – spremljaj, pripravi|2 h/teden|
|**Poslovni načrt** (1–2 strani)|4 h (enkrat)|

**Rezultat:** **Prvi plačan posel + partnerji kontaktirani + poslovni načrt.**

---

## 4. Dnevni ritem – **konkretno**

### Delovni dan (4 h)

|Čas|Kaj|Trajanje|
|---|---|---|
|**9.00–11.00**|**Tehnični tir** – koda, testi|2 h|
|**11.00–11.15**|Odmor|15 min|
|**11.15–12.00**|**Tehnični tir** – koda, testi|45 min|
|**12.00–13.00**|Kosilo + odmor|1 h|
|**13.00–14.00**|**Poslovni tir** – predlogi, portfolio, LinkedIn|1 h|
|**14.00–14.15**|**Dnevnik** – kaj si naredil, kaj sledi|15 min|
|**14.15**|**Nehaj**|–|

**Skupaj:** 2,75 h tehnično + 1 h poslovno + 15 min dnevnik = **4 h**.

### Tedenski ritem

|Dan|Tehnični fokus|Poslovni fokus|
|---|---|---|
|**Ponedeljek**|Koda|5 predlogov|
|**Torek**|Koda|5 predlogov + LinkedIn|
|**Sreda**|Koda|5 predlogov + klici|
|**Četrtek**|Koda|5 predlogov|
|**Petek**|Koda + testi|5 predlogov + pregled tedna|
|**Sobota**|–|Ples (mreža)|
|**Nedelja**|–|Počitek|