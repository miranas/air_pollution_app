#!/usr/bin/env bash
# archflow-open.sh – odpre že izdelano animacijo v brskalniku
# Uporaba: bash docs/arhitektura/archflow/archflow-open.sh

# Absolutna pot do mape, kjer je ta skripta
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT="$SCRIPT_DIR/architecture-report.html"

if [ ! -f "$REPORT" ]; then
    echo "❌ $REPORT ne obstaja."
    echo "   Najprej zaženi: bash $SCRIPT_DIR/archflow.sh"
    exit 1
fi

echo "🌐 Odpiram $REPORT..."

# Preveri, kateri brskalnik je na voljo (Linux, macOS, Windows)
if command -v xdg-open &> /dev/null; then
    xdg-open "$REPORT"          # Linux
elif command -v open &> /dev/null; then
    open "$REPORT"               # macOS
elif command -v start &> /dev/null; then
    start "$REPORT"              # Windows (Git Bash)
elif command -v firefox &> /dev/null; then
    firefox "$REPORT" &          # Firefox (fallback)
else
    echo "⚠️ Ne najdem brskalnika. Odpri ročno: $REPORT"
fi