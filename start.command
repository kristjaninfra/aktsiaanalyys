#!/bin/bash
# Topeltklõpsa, et käivitada aktsiaanalüüs. Sulge aken, et peatada.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Esmakordne seadistus…"
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/streamlit run app.py --browser.gatherUsageStats false
