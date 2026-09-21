#!/usr/bin/env bash
set -e
# Simple runner: prefers Python (always available), falls back to R
if command -v python3 >/dev/null 2>&1 && python3 -c "import lifelines" 2>/dev/null; then
  echo "Running Python pipeline..."
  python3 cml_survival_correction.py
elif command -v Rscript >/dev/null 2>&1; then
  echo "Running R pipeline..."
  Rscript cml_survival_correction.R
else
  echo "Installing Python deps then running..."
  pip install --break-system-packages -r requirements.txt
  python3 cml_survival_correction.py
fi
ls -lh output/
