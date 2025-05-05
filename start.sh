#!/bin/bash
set -e  # Script beendet sich bei Fehlern

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Virtuelle Umgebung aktivieren
if [ -f "./venv/bin/activate" ]; then
    source ./venv/bin/activate
else
    echo "Fehler: virtuelle Umgebung nicht gefunden."
    exit 1
fi

# Set Django settings module
export DJANGO_SETTINGS_MODULE=buzzer.settings

# Daphne starten
exec daphne -b 0.0.0.0 -p 8080 buzzer.asgi:application