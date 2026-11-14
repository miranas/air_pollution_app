#!/bin/bash
# Tunel na Hetzner – Ollama, PostgreSQL, Redis

echo "Odpiram tunel na Hetzner..."
echo "Porti: 11434 (Ollama), 5432 (PostgreSQL), 6379 (Redis)"
echo "Pusti to okno odprto. Ctrl+C za zaprtje."
echo ""

ssh -L 11434:127.0.0.1:11434 \
    -L 5432:127.0.0.1:5432 \
    -L 6379:127.0.0.1:6379 \
    Hetzner
