#!/bin/bash
# Zbozi.cz Dashboard Analyzer – spuštění
cd "$(dirname "$0")"
source venv/bin/activate

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Zbozi.cz Dashboard Analyzer            ║"
echo "  ║   http://localhost:5055                   ║"
echo "  ║                                           ║"
echo "  ║   Otevrete prohlizec na adrese vyse.      ║"
echo "  ║   Pro ukonceni stisknete Ctrl+C           ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

python app.py
