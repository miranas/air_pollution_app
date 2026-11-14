#!/usr/bin/env bash
# Prebere DEEPSEEK_API_KEY iz .env in izpiše samo vrednost
grep -E '^DEEPSEEK_API_KEY=' /home/miran/Documents/air_pollution_app/.env | cut -d'=' -f2- | tr -d '"' | tr -d "'"
