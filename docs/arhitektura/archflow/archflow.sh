#!/usr/bin/env bash
# archflow.sh – požene archflow od začetka do konca, brez prekinitev
# Uporaba: bash docs/arhitektura/archflow/archflow.sh

set -e

# 1. Pojdi v koren projekta
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
cd "$PROJECT_DIR" || { echo "❌ $PROJECT_DIR ne obstaja."; exit 1; }
echo "📁 Projekt: $(pwd)"

# 2. Nastavi pot do docs mape
DOCS_DIR="$SCRIPT_DIR"
mkdir -p "$DOCS_DIR"

# 3. Preveri .env
if [ ! -f .env ]; then
    echo "❌ .env ne obstaja v $(pwd)"
    echo "   Ustvari .env z: DEEPSEEK_API_KEY=sk-..."
    exit 1
fi

# 4. Uvozi .env
set -a
source .env
set +a

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ DEEPSEEK_API_KEY ni nastavljen v .env"
    exit 1
fi

# 5. Preveri claude
if ! command -v claude &> /dev/null; then
    echo "❌ Claude Code ni nameščen. Namesti z: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# 6. Nastavi okolje za Claude Code + DeepSeek
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
export ANTHROPIC_MODEL=deepseek-chat
export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-chat
export ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-chat
export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-chat

echo "✅ Okolje nastavljeno (DeepSeek, model: $ANTHROPIC_MODEL)"
echo ""

# 7. Zaženi archflow prek Claude Code BREZ potrjevanja
echo "🚀 Zaganjam archflow (brez potrjevanja)..."
claude --dangerously-skip-permissions -p "Use the archflow skill to analyze this codebase and generate the architecture report. Run the full pipeline: validate, render, verify. When done, ensure the animation script is present in architecture-report.html (function activate, chapterNav, afh-chapters). If the animation script is missing, copy it from architecture-report.template.html into architecture-report.html before </body>. Then confirm architecture-report.html exists and is complete."

# 8. Preveri, ali je architecture-report.html nastal
if [ ! -f architecture-report.html ]; then
    echo "❌ architecture-report.html ni nastal. Preveri loge Claude Code."
    exit 1
fi

# 9. Preveri, ali animacijski skript manjka; če manjka, ga dodaj
if ! grep -q "function activate" architecture-report.html; then
    echo "🔧 Animacijski skript manjka, dodajam iz predloge..."
    if [ -f architecture-report.template.html ]; then
        python3 - <<'PYEOF'
import re

with open('architecture-report.template.html', 'r', encoding='utf-8') as f:
    template = f.read()

with open('architecture-report.html', 'r', encoding='utf-8') as f:
    html = f.read()

scripts = re.findall(r'<script>.*?</script>', template, re.DOTALL)
anim_script = None
for s in scripts:
    if 'function activate' in s:
        anim_script = s
        break

if not anim_script:
    print("❌ V predlogi ni animacijskega skripta.")
    exit(1)

if '</body>' not in html:
    print("❌ </body> ne obstaja v HTML-ju.")
    exit(1)

html = html.replace('</body>', anim_script + '\n</body>', 1)

with open('architecture-report.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("✅ Animacijski skript dodan.")
PYEOF
    else
        echo "⚠️ architecture-report.template.html ne obstaja, ne morem dodati skripta."
    fi
else
    echo "✅ Animacijski skript že prisoten."
fi

# 10. Premakni datoteke v docs/ (če so v korenu)
if [ -f "$PROJECT_DIR/architecture-report.html" ]; then
    mv "$PROJECT_DIR/architecture-report.html" "$DOCS_DIR/"
fi
if [ -f "$PROJECT_DIR/architecture-report.hero.json" ]; then
    mv "$PROJECT_DIR/architecture-report.hero.json" "$DOCS_DIR/"
fi
if [ -f "$PROJECT_DIR/architecture-report.template.html" ]; then
    mv "$PROJECT_DIR/architecture-report.template.html" "$DOCS_DIR/"
fi

echo "📁 Datoteke premaknjene v: $DOCS_DIR"

# 11. Odpri v brskalniku
echo "🌐 Odpiram architecture-report.html v brskalniku..."
if command -v xdg-open &> /dev/null; then
    xdg-open "$DOCS_DIR/architecture-report.html"
elif command -v firefox &> /dev/null; then
    firefox "$DOCS_DIR/architecture-report.html" &
else
    echo "⚠️ Ne najdem xdg-open ali firefox. Odpri ročno: $DOCS_DIR/architecture-report.html"
fi

echo ""
echo "✅ Končano."
echo "   Poročilo: $DOCS_DIR/architecture-report.html"