#!/bin/bash
# Zbozi.cz Analyzer – spuštění serveru
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

echo "========================================"
echo "  Zbozi.cz Analyzer"
echo "  http://localhost:5055"
echo "========================================"
python app.py
