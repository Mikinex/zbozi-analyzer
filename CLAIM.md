# Zbozi.cz Dashboard Analyzer – Claim & Handover

## Popis produktu

**Zbozi.cz Dashboard Analyzer** je webový analytický nastroj pro provozovatele e-shopu na platforme Zbozi.cz. Umoznuje komplexni analyzu obchodu pres oficialni Zbozi.cz API v1 a automaticke stazeni a parsovani XML feedu.

---

## Architektura

| Vrstva | Technologie | Soubor |
|--------|------------|--------|
| Frontend | HTML5 + Bootstrap 5 + Chart.js | `templates/index.html` |
| Backend | Python 3 + Flask | `app.py` |
| API klient | requests + Basic Auth | `zbozi_api.py` |
| Analyticke jadro | Python dataclasses | `analyzer.py` |

---

## Klicove funkce

### 1. Automaticka analyza (endpoint `/analyze`)
- Diagnostika feedu (`/v1/shop/diagnostics/item`)
- Stazeni a parsovani XML feedu (URL z `/v1/shop/feeds`)
- Polozky s paginaci po 30 (`/v1/shop/items` s `loadProductDetail`)
- Obohaceni polozek daty z XML feedu (cena, EAN, parametry, dostupnost)
- Konkurencni data z `/v1/products/{ids}`
- Statistiky (agregovane, dle kategorii, dle zarizeni)
- Recenze obchodu a produktu (max 180 dni zpet)
- Kampan a bidding info
- Parametry kategorii
- Automaticka doporuceni (feed + Sklik Nakupy)

### 2. API Explorer (endpoint `/api/call`)
Primny pristup ke vsem 23 endpointum Zbozi.cz API:

| Skupina | Endpointy |
|---------|-----------|
| Diagnostika | `diagnostics` |
| Polozky | `items` (max 30, s detailem), `items_basic` (max 3000) |
| Feed | `feeds`, `feed_download` (stahne a rozparsuje XML) |
| Kampan | `campaign`, `bidding` |
| Statistiky | `stats_aggregated`, `stats_category`, `stats_context`, `stats_item_list`, `stats_item_json` |
| Recenze | `reviews`, `product_reviews` |
| Katalog | `products`, `categories`, `categories_tree` |
| Vyrobci | `manufacturers`, `manufacturers_search`, `manufacturers_by_ids` |
| Eshopy | `shops` |

### 3. Dashboard UI (8 tabu)
1. **Prehled** – KPI dlazdice, donut grafy, kampan, feed, diagnostika
2. **Statistiky** – denni graf, zarizeni, souhrn vykonu
3. **Kategorie** – bar chart, detailni tabulka s CTR/CPC gap
4. **Polozky** – tabulka s filtry (sparovane, bez parametru, drazsi)
5. **Recenze** – hodnoceni obchodu + produktove recenze
6. **Doporuceni** – feed & XML tipy, Sklik Nakupy strategie
7. **API stav** – status vsech endpointu, varovani
8. **API Explorer** – interaktivni volani endpointu

---

## Datovy tok

```
1. Uzivatel zada shop_id + api_key
2. /v1/shop/feeds → ziskame feed URL
3. HTTP GET feed URL → stahneme XML feed → parsujeme SHOPITEM elementy
4. /v1/shop/items (po strankach 30) → zakladni data polozek
5. Obohaceni: XML feed data → polozky (cena, EAN, parametry, dostupnost, URL, obrazek)
6. /v1/products/{ids} (davky po 10) → konkurencni data (shopCount, minPrice)
7. Statistiky, recenze, kampan → doplnkova data
8. Analyza kategorii + generovani doporuceni
9. JSON odpoved → renderovani v dashboardu
```

---

## Omezeni API

| Parametr | Omezeni |
|----------|---------|
| `items` s `loadProductDetail` | max 30 polozek na pozadavek |
| `items` s `loadSearchInfo` | max 300 polozek na pozadavek |
| `items` bez detailu | max 3000 polozek na pozadavek |
| `reviews` / `product_reviews` | `timestampFrom` max 180 dni zpet |
| `products/{ids}` | max 10 ID najednou |
| `categories/{ids}` | max 10 ID najednou |
| Rate limit | 2 sekundy mezi pozadavky |

---

## Bezpecnost

- API klice se neukladaji na serveru
- Basic Auth pres HTTPS
- Zadna perzistence dat – vse v pameti po dobu requestu

---

## Spusteni

```bash
pip install flask requests
python app.py
# Dashboard na http://localhost:5055
```

---

## Dulezite: API api.zbozi.cz bude vypnuto 16. 3. 2026

Migrace na Sklik API: https://api.sklik.cz/

---

*Vygenerovano: 2026-02-24*
*Verze: 1.0*
