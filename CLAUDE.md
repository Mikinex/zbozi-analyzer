# Zbozi.cz Dashboard Analyzer

## Jazyk
Vždy odpovídej česky. Uživatel je netechnický – vysvětluj jednoduše, bez žargonu.

## Projekt
- Flask webová aplikace pro analýzu e-shopu na Zboží.cz
- Backend: `app.py` (Flask), `analyzer.py` (analytické jádro), `zbozi_api.py` (API klient)
- Frontend: `templates/index.html` (Bootstrap 5 + Chart.js)
- Virtuální prostředí: `venv/` (Python 3.9)

## Spuštění
```bash
source venv/bin/activate && python app.py
# Dashboard běží na http://localhost:5055
```

## Klíčové limity Zboží.cz API
- `/v1/shop/items` s `loadProductDetail`: max 30 položek/request
- Recenze (`reviews`, `product-reviews`): max 180 dní zpět
- `/v1/products/{ids}`: max 10 ID najednou
- Rate limit: 2 sekundy mezi požadavky
- **API bude vypnuto 16. 3. 2026** – migrace na Sklik API

## Datový tok
1. `/v1/shop/feeds` → získání feed URL
2. HTTP GET feed URL → stažení a parsování XML feedu (ceny, EAN, parametry, dostupnost)
3. `/v1/shop/items` po stránkách (30/request) → základní data položek
4. Obohacení položek daty z XML feedu
5. `/v1/products/{ids}` v dávkách → konkurenční data
6. Statistiky, recenze, kampaň → doplňková data

## Konvence
- Commit messages česky
- Kód a komentáře v kódu anglicky/česky dle kontextu
- Při chybě vysvětli co se stalo a jak to opravit jednoduchým jazykem
