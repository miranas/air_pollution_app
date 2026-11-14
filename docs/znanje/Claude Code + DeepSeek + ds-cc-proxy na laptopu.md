

### Namen

Claude Code naj uporablja **DeepSeek model** namesto Anthropicovega. Proxy `ds-cc-proxy` poskrbi za **~40 % cenejše podnaloge** in odpravi napake `400`.

### Predpogoji

- Linux (Fedora)
    
- `pyenv` ali `uv` za Python
    
- `claude` (Claude Code) nameščen
    
- DeepSeek API ključ
    

---

### 1. Namesti Claude Code

bash

curl -fsSL https://claude.ai/install.sh | bash

Po namestitvi **odpri nov terminal** in preveri:

bash

claude --version

---

### 2. Namesti `ds-cc-proxy` (globalno, ne v pyenv)

bash

uv tool install ds-cc-proxy

Preveri pot:

bash

which ds-cc-proxy
# Pričakovano: /home/<user>/.local/bin/ds-cc-proxy

**Zakaj globalno:** Da systemd najde proxy brez `pyenv` odvisnosti.

---

### 3. Ustvari skripto za branje ključa iz `.env`

bash

mkdir -p ~/Documents/air_pollution_app/scripts
nano ~/Documents/air_pollution_app/scripts/get-deepseek-key.sh

Vsebina:

bash

#!/usr/bin/env bash
grep -E '^DEEPSEEK_API_KEY=' /home/<user>/Documents/air_pollution_app/.env | cut -d'=' -f2- | tr -d '"' | tr -d "'"

Naredi izvršljivo:

bash

chmod +x ~/Documents/air_pollution_app/scripts/get-deepseek-key.sh

Preveri, da izpiše ključ:

bash

bash ~/Documents/air_pollution_app/scripts/get-deepseek-key.sh

**Pomembno:** `.env` mora vsebovati `DEEPSEEK_API_KEY=sk-...`.

---

### 4. Konfiguriraj Claude Code (`~/.claude/settings.json`)

bash

nano ~/.claude/settings.json

Vsebina:

json

{
  "permissions": {
    "allow": [
      "Bash(node /home/<user>/.claude/plugins/marketplaces/archflow/plugins/archflow/skills/archflow/scripts/hero-diagram.mjs render architecture-report.hero.json architecture-report.html --template architecture-report.template.html --repo-root . --json)"
    ]
  },
  "apiKeyHelper": "/home/<user>/Documents/air_pollution_app/scripts/get-deepseek-key.sh",
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:16889",
    "ANTHROPIC_MODEL": "deepseek-flash[1m]",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-flash[1m]",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-flash[1m]",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-flash"
  }
}

**Zamenjaj `<user>`** z svojim uporabniškim imenom.

**Zakaj `[1m]`:** Claude Code prepozna 1M kontekst, ne privzame 200k.

---

### 5. Ustvari systemd storitev za proxy

bash

mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/ds-cc-proxy.service

Vsebina:

ini

[Unit]
Description=ds-cc-proxy (DeepSeek Anthropic API Proxy)
After=network.target
[Service]
Type=simple
ExecStart=/home/<user>/.local/bin/ds-cc-proxy
Restart=on-failure
RestartSec=5
[Install]
WantedBy=default.target

Omogoči in zaženi:

bash

systemctl --user daemon-reload
systemctl --user enable ds-cc-proxy.service
systemctl --user start ds-cc-proxy.service

Preveri:

bash

systemctl --user status ds-cc-proxy.service
# Pričakovano: active (running)

---

### 6. Preveri, da vse dela

bash

# Proxy health
curl http://localhost:16889/health
# Pričakovano: {"status":"ok",...}
# Zaženi Claude Code
cd ~/Documents/air_pollution_app
claude

V vrstici stanja mora pisati:

text

deepseek-flash[1m] · API Usage Billing

---

## 🔍 Kaj točno dela (in kaj ne)

|Kaj|Deluje?|Opomba|
|---|---|---|
|**Claude Code z DeepSeek**|✅|Prek `ANTHROPIC_BASE_URL`|
|**~40 % cenejše podnaloge**|✅|Proxy preusmeri sub-agente na Flash|
|**Odprava napak 400**|✅|Proxy popravi `thinking` bloke|
|**Tvoj LangGraph agent**|❌|Proxy je samo za Claude Code – agent kliče DeepSeek neposredno|

---

## ⚠️ Kaj storiti, če ne dela

|Težava|Rešitev|
|---|---|
|`claude: command not found`|Odpri nov terminal ali dodaj `~/.local/bin` v `PATH`|
|`apiKeyHelper failed: exited 127`|Skripta ne obstaja ali ni izvršljiva|
|`Model "deepseek-flash" isn't recognized`|Dodaj `[1m]` v ime modela|
|Proxy ne teče|`systemctl --user status ds-cc-proxy`|
|`401 Unauthorized`|Skripta ne izpiše ključa – preveri `.env`|

---

## 📋 Povzetek v enem stavku

**Claude Code + DeepSeek = `ANTHROPIC_BASE_URL` na proxy + `apiKeyHelper` za ključ + systemd za samodejni zagon proxyja.** Brez tega Claude Code ne dela z DeepSeekom, s tem pa dobiš cenejše podnaloge in stabilnejše delovanje.

---

Shrani ta povzetek v `docs/ops/claude-deepseek-setup.md`. Na novi mašini samo slediš korakom 1–6 in imaš enako okolje. Če se pri katerem koraku zatakne, pošlji izpis napake – na podlagi tega bova ugotovila, kaj manjka.