from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
import time

from zbozi_api import ZboziAPI, ZboziAPIError


@dataclass
class Recommendation:
    priority: str          # 'critical' | 'important' | 'tip'
    section: str
    title: str
    detail: str
    example: Optional[str] = None
    affected: int = 0


@dataclass
class AnalysisReport:
    shop_id: str
    generated_at: str

    # ── Souhrnné počty ──────────────────────────────────────
    items_total: int = 0
    items_paired: int = 0
    items_errors: int = 0
    items_improvements: int = 0
    items_ok: int = 0

    # ── Výkon celkem (30 dní) ────────────────────────────────
    perf_views: int = 0
    perf_clicks: int = 0
    perf_cost: float = 0.0
    perf_conversions: int = 0
    perf_avg_cpc: float = 0.0
    perf_ctr: float = 0.0
    perf_conv_rate: float = 0.0

    # ── Recenze ─────────────────────────────────────────────
    reviews_total: int = 0
    reviews_avg_rating: float = 0.0
    reviews_positive: int = 0
    reviews_negative: int = 0
    reviews_list: List[Dict] = field(default_factory=list)
    product_reviews_list: List[Dict] = field(default_factory=list)

    # ── Konkurenční analýza ─────────────────────────────────
    competition_summary: Dict = field(default_factory=dict)
    categories_analysis: List[Dict] = field(default_factory=list)
    items_price_worse: int = 0
    items_price_ok: int = 0
    items_no_delivery: int = 0
    items_no_params: int = 0
    items_no_ean: int = 0

    # ── Feed data (z XML) ─────────────────────────────────
    feed_items_by_id: Dict = field(default_factory=dict)
    feed_quality: Dict = field(default_factory=dict)  # analýza kvality feedu

    # ── Raw data pro dashboard ───────────────────────────────
    raw_items: List[Dict] = field(default_factory=list)
    raw_stats_daily: List[Dict] = field(default_factory=list)
    raw_diagnostics: Dict = field(default_factory=dict)

    # ── Strukturované výsledky ───────────────────────────────
    feed_recommendations: List[Recommendation] = field(default_factory=list)
    sklik_recommendations: List[Recommendation] = field(default_factory=list)
    top_categories_by_clicks: List[Dict] = field(default_factory=list)
    device_stats: List[Dict] = field(default_factory=list)
    feeds_info: List[Dict] = field(default_factory=list)
    campaign_info: Dict = field(default_factory=dict)
    category_params: Dict = field(default_factory=dict)

    # ── Stav API ─────────────────────────────────────────────
    endpoint_status: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
class ZboziAnalyzer:

    def __init__(self, api: ZboziAPI):
        self.api = api

    def analyze(self, shop_id: str) -> AnalysisReport:
        report = AnalysisReport(
            shop_id=shop_id,
            generated_at=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        )
        self._fetch_diagnostics(report)
        self._fetch_feeds(report)
        self._fetch_feed_content(report)
        self._fetch_items(report)
        self._enrich_items_from_feed(report)
        self._fetch_product_details(report)
        self._fetch_campaign(report)
        self._fetch_stats_aggregated(report)
        self._fetch_stats_category(report)
        self._fetch_stats_context(report)
        self._fetch_reviews(report)
        self._fetch_category_params(report)

        self._analyze_feed_quality(report)
        self._analyze_categories(report)
        self._build_feed_recommendations(report)
        self._build_sklik_recommendations(report)
        return report

    # ─────────────────────────────────────────────────────────
    # Bezpečné volání API
    # ─────────────────────────────────────────────────────────

    def _safe(self, name: str, report: AnalysisReport, fn):
        try:
            result = fn()
            report.endpoint_status[name] = "ok"
            return result
        except ZboziAPIError as e:
            report.endpoint_status[name] = str(e)
            report.warnings.append(f"{name}: {e}")
            return None
        except Exception as e:
            report.endpoint_status[name] = f"Chyba: {e}"
            report.warnings.append(f"{name}: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # Číselné utility
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _num(val) -> float:
        """Sečte hodnoty pokud je val dict (nested views/clicks/cost objekty)."""
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict):
            nums = [v for v in val.values() if isinstance(v, (int, float))]
            return float(sum(nums)) if nums else 0.0
        return 0.0

    def _m(self, row: dict, *keys) -> float:
        """První nalezená metrika z řádku."""
        for k in keys:
            if k in row:
                return self._num(row[k])
        return 0.0

    @staticmethod
    def _halere(val: float, total_clicks: float) -> float:
        """Heuristika: pokud průměrné CPC > 1000, API vrátí haléře → dělit 100."""
        if total_clicks > 0 and val / total_clicks > 1000:
            return val / 100.0
        return val

    # ─────────────────────────────────────────────────────────
    # Fetching – Diagnostika
    # ─────────────────────────────────────────────────────────

    def _fetch_diagnostics(self, report: AnalysisReport):
        data = self._safe("diagnostics", report, self.api.get_diagnostics)
        if not data:
            return
        d = data if isinstance(data, dict) else {}
        report.raw_diagnostics = d

        # API vrací: total, ok, okPercentage, canBeImproved, canBeImprovedPercentage,
        # error, errorPercentage, notVisible, notVisiblePercentage
        report.items_total = int(d.get("total", 0))
        report.items_ok = int(d.get("ok", 0))
        report.items_errors = int(d.get("error", 0))
        report.items_improvements = int(d.get("canBeImproved", 0))

    # ─────────────────────────────────────────────────────────
    # Fetching – Položky
    # ─────────────────────────────────────────────────────────

    def _normalize_item(self, item: dict) -> dict:
        # Párování: product objekt z API nebo matchingId = spárováno
        # Na Zboží.cz má každá nabídka produktovou kartu (auto/manuální)
        product = item.get("product")
        paired = (product is not None and isinstance(product, dict)) or bool(item.get("matchingId"))

        product_id = None
        top_position = None
        from_cheapest_position = None
        cat_id = item.get("categoryId")

        if product and isinstance(product, dict):
            product_id = product.get("productId")
            if not cat_id:
                cat_id = product.get("categoryId")
            pdi = product.get("productDetailInfo") or {}
            top_position = pdi.get("topPosition")
            from_cheapest_position = pdi.get("fromCheapestPosition")

        max_cpc = item.get("maxCpcSearch")

        # Cena – z item nebo product
        price = item.get("price")
        if price is None and product and isinstance(product, dict):
            price = product.get("price")
        if price is not None:
            price = float(price)

        # Dostupnost
        delivery_date = item.get("deliveryDate")
        has_delivery = delivery_date is not None

        # Parametry a EAN
        has_params = bool(item.get("params") or item.get("parameters"))
        has_ean = bool(item.get("ean"))

        # Suggested CPC z searchInfo
        search_info = item.get("searchInfo") or {}
        suggested_cpc = search_info.get("suggestedCpc")
        if suggested_cpc is not None:
            suggested_cpc = float(suggested_cpc)

        return {
            "id": str(item.get("itemId") or ""),
            "name": item.get("name") or "—",
            "price": price,
            "paired": paired,
            "productId": product_id,
            "category": "",  # nemáme název z items API
            "categoryId": cat_id,
            "manufacturer": str(item.get("manufacturerId") or ""),
            "delivery": delivery_date,
            "hasDelivery": has_delivery,
            "hasParams": has_params,
            "hasEan": has_ean,
            "maxCpc": float(max_cpc) if max_cpc is not None else None,
            "topPosition": top_position,
            "fromCheapestPosition": from_cheapest_position,
            "url": item.get("url") or "",
            "img": item.get("imgUrl") or "",
            # Konkurenční data – doplní se z /v1/products/{ids}
            "shopCount": None,
            "minPrice": None,
            "maxPrice": None,
            "priceVsMin": None,
            "suggestedCpc": suggested_cpc,
            "topRank": top_position,
            "productRating": None,
            "productRatingCount": None,
        }

    def _fetch_items(self, report: AnalysisReport):
        all_items = []

        # 1) Zkusit items/basic (limit 3000)
        data = self._safe("items_basic", report, lambda: self.api.get_items_basic(limit=3000, offset=0))
        if data and isinstance(data.get("data"), list):
            all_items = data["data"]
            total = data.get("totalCount", len(all_items))
            # Další stránky
            while len(all_items) < total:
                offset = len(all_items)
                page = self._safe(f"items_p{offset}", report,
                                  lambda o=offset: self.api.get_items_basic(limit=3000, offset=o))
                if not page or not isinstance(page.get("data"), list) or not page["data"]:
                    break
                all_items.extend(page["data"])

        # 2) Pokud items/basic selhal, zkusit normální items (limit 30, prvních 300)
        if not all_items:
            for offset in range(0, 300, 30):
                cur_offset = offset
                data = self._safe(f"items_{offset}", report,
                                  lambda o=cur_offset: self.api.get_items(limit=30, offset=o,
                                                                          load_product_detail=False,
                                                                          load_search_info=False))
                if not data or not isinstance(data.get("data"), list) or not data["data"]:
                    break
                all_items.extend(data["data"])

        # 3) Pokud máme feed, doplnit položky které chybí v API
        if report.feed_items_by_id:
            api_ids = {str(item.get("itemId", "")) for item in all_items}
            for fid, fdata in report.feed_items_by_id.items():
                if fid not in api_ids:
                    # Vytvořit pseudo-API item z feedu
                    # Všechny položky ve feedu jsou spárované na Zboží.cz
                    all_items.append({
                        "itemId": fid,
                        "name": fdata.get("productName", ""),
                        "categoryId": None,
                        "condition": "new",
                        "matchingId": "feed",
                        "from_feed": True,
                    })

        report.items_total = max(report.items_total, len(all_items))
        report.endpoint_status["items"] = f"ok ({len(all_items)} položek)"

        paired = 0
        normalized = []
        for item in all_items:
            n = self._normalize_item(item)
            if n["paired"]:
                paired += 1
            normalized.append(n)

        report.items_paired = paired
        report.items_no_delivery = sum(1 for n in normalized if not n["hasDelivery"])
        report.items_no_params = sum(1 for n in normalized if not n["hasParams"])
        report.items_no_ean = sum(1 for n in normalized if not n["hasEan"])
        report.raw_items = normalized

    # ─────────────────────────────────────────────────────────
    # Fetching – Product details (konkurenční data)
    # ─────────────────────────────────────────────────────────

    def _fetch_product_details(self, report: AnalysisReport):
        """Doplní shopCount, minPrice, maxPrice z /v1/products/{ids}."""
        # Sesbírat unikátní productIds
        product_ids = []
        seen = set()
        for item in report.raw_items:
            pid = item.get("productId")
            if pid and pid not in seen:
                seen.add(pid)
                product_ids.append(pid)

        if not product_ids:
            return

        # Omezit na max 500 produktů (50 batchů × 2s = ~2 min)
        product_ids = product_ids[:500]

        # Volat API po dávkách max 10
        product_data = {}  # productId -> {shopCount, minPrice, maxPrice}
        for i in range(0, len(product_ids), 10):
            batch = product_ids[i:i+10]
            data = self._safe(
                f"products_batch_{i//10}",
                report,
                lambda b=batch: self.api.get_products(b)
            )
            if not data:
                continue
            # Odpověď je list produktů nebo dict
            products = data if isinstance(data, list) else data.get("data", data)
            if isinstance(products, list):
                for p in products:
                    pid = p.get("productId") or p.get("id")
                    if pid:
                        product_data[pid] = {
                            "shopCount": p.get("shopCount"),
                            "minPrice": p.get("minPrice"),
                            "maxPrice": p.get("maxPrice"),
                        }
            elif isinstance(products, dict) and "shopCount" in products:
                # Jediný produkt
                pid = products.get("productId") or products.get("id")
                if pid:
                    product_data[pid] = {
                        "shopCount": products.get("shopCount"),
                        "minPrice": products.get("minPrice"),
                        "maxPrice": products.get("maxPrice"),
                    }

        # Propojit zpět s položkami
        for item in report.raw_items:
            pid = item.get("productId")
            if pid and pid in product_data:
                pd = product_data[pid]
                item["shopCount"] = pd["shopCount"]
                item["minPrice"] = pd["minPrice"]
                item["maxPrice"] = pd["maxPrice"]
                # Spočítat priceVsMin pokud máme cenu položky
                if item.get("price") and pd["minPrice"] and pd["minPrice"] > 0:
                    item["priceVsMin"] = round(float(item["price"]) / float(pd["minPrice"]), 3)

        # Přepočítat cenové metriky
        report.items_price_worse = sum(1 for n in report.raw_items if n.get("priceVsMin") and n["priceVsMin"] > 1.05)
        report.items_price_ok = sum(1 for n in report.raw_items if n.get("priceVsMin") and n["priceVsMin"] <= 1.05)

    # ─────────────────────────────────────────────────────────
    # Fetching – Feedy, Kampaň
    # ─────────────────────────────────────────────────────────

    def _fetch_feeds(self, report: AnalysisReport):
        data = self._safe("feeds", report, self.api.get_feeds)
        if not data:
            return
        feeds = data.get("data", data)
        if isinstance(feeds, list):
            # Normalizovat timestamp na čitelný datum
            for f in feeds:
                ts = f.get("lastSuccessfulImport")
                if isinstance(ts, (int, float)) and ts > 0:
                    f["lastSuccessfulImportFormatted"] = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
            report.feeds_info = feeds
        elif isinstance(feeds, dict):
            ts = feeds.get("lastSuccessfulImport")
            if isinstance(ts, (int, float)) and ts > 0:
                feeds["lastSuccessfulImportFormatted"] = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
            report.feeds_info = [feeds]

    def _fetch_feed_content(self, report: AnalysisReport):
        """Stáhne XML feed a uloží rozparsované položky do feed_items_by_id."""
        if not report.feeds_info:
            return
        for feed in report.feeds_info:
            feed_url = feed.get("feedUrl") or feed.get("url")
            if not feed_url:
                continue
            try:
                feed_items = self.api.download_feed(feed_url)
                for fi in feed_items:
                    iid = fi.get("itemId")
                    if iid:
                        report.feed_items_by_id[str(iid)] = fi
                report.endpoint_status["feed_download"] = f"ok ({len(feed_items)} položek)"
            except Exception as e:
                report.endpoint_status["feed_download"] = str(e)
                report.warnings.append(f"feed_download: {e}")
            break  # Stačí první feed

    def _enrich_items_from_feed(self, report: AnalysisReport):
        """Obohatí normalizované položky daty z XML feedu."""
        if not report.feed_items_by_id:
            return
        for item in report.raw_items:
            fi = report.feed_items_by_id.get(item["id"])
            if not fi:
                continue
            # Cena
            if item["price"] is None and fi.get("price") is not None:
                item["price"] = fi["price"]
            # Dostupnost
            if not item["hasDelivery"] and fi.get("deliveryDate") is not None:
                item["delivery"] = fi["deliveryDate"]
                item["hasDelivery"] = True
            # EAN
            if not item["hasEan"] and fi.get("ean"):
                item["hasEan"] = True
            # Parametry
            if not item["hasParams"] and fi.get("params"):
                item["hasParams"] = bool(fi["params"])
            # URL, obrázek
            if not item["url"] and fi.get("url"):
                item["url"] = fi["url"]
            if not item["img"] and fi.get("imgUrl"):
                item["img"] = fi["imgUrl"]
            # Kategorie text
            if not item["category"] and fi.get("categoryText"):
                item["category"] = fi["categoryText"]
            # Manufacturer
            if (not item["manufacturer"] or item["manufacturer"] == "") and fi.get("manufacturer"):
                item["manufacturer"] = fi["manufacturer"]

        # Přepočítat metriky po obohacení
        report.items_no_delivery = sum(1 for n in report.raw_items if not n["hasDelivery"])
        report.items_no_params = sum(1 for n in report.raw_items if not n["hasParams"])
        report.items_no_ean = sum(1 for n in report.raw_items if not n["hasEan"])

    def _fetch_campaign(self, report: AnalysisReport):
        data = self._safe("campaign", report, self.api.get_campaign)
        if not data:
            return
        d = data if isinstance(data, dict) else {}
        # Normalizovat: creditWithoutVAT, creditWithVAT, limit.duration/value/spent/exceeded
        campaign = {}
        for key in ("creditWithoutVAT", "creditWithVAT"):
            if key in d:
                campaign[key] = d[key]
        limit = d.get("limit")
        if isinstance(limit, dict):
            campaign["limit"] = limit
        report.campaign_info = campaign if campaign else d

    # ─────────────────────────────────────────────────────────
    # Fetching – Statistiky
    # ─────────────────────────────────────────────────────────

    def _fetch_stats_aggregated(self, report: AnalysisReport):
        data = self._safe("stats_aggregated", report, lambda: self.api.get_stats_aggregated(30))
        if not data:
            return
        try:
            rows = data.get("data", [])
            if not isinstance(rows, list) or not rows:
                return

            # views/clicks/cost/conversions jsou nested objekty – sečíst
            views = sum(self._m(r, "views") for r in rows)
            clicks = sum(self._m(r, "clicks") for r in rows)
            cost_raw = sum(self._m(r, "cost") for r in rows)
            convs = sum(self._m(r, "conversions") for r in rows)

            cost = self._halere(cost_raw, clicks)

            report.perf_views = int(views)
            report.perf_clicks = int(clicks)
            report.perf_cost = round(cost, 2)
            report.perf_conversions = int(convs)
            if clicks > 0:
                report.perf_avg_cpc = round(cost / clicks, 2)
            if views > 0:
                report.perf_ctr = round(clicks / views * 100, 2)
            if clicks > 0:
                report.perf_conv_rate = round(convs / clicks * 100, 2)

            # Denní řádky pro graf – startTimestamp (ne date/timestamp)
            daily = []
            for r in rows:
                ts = r.get("startTimestamp")
                if isinstance(ts, (int, float)):
                    date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                else:
                    date_str = str(ts or "")
                rc = self._m(r, "cost")
                r_clicks = max(self._m(r, "clicks"), 1)
                daily.append({
                    "date": date_str,
                    "views": int(self._m(r, "views")),
                    "clicks": int(self._m(r, "clicks")),
                    "cost": round(self._halere(rc, r_clicks), 2),
                    "conversions": int(self._m(r, "conversions")),
                })
            report.raw_stats_daily = daily
        except Exception as e:
            report.warnings.append(f"stats_aggregated: {e}")

    def _fetch_stats_category(self, report: AnalysisReport):
        data = self._safe("stats_category", report, lambda: self.api.get_stats_category(30))
        if not data:
            return
        try:
            rows = data.get("data", [])
            if not isinstance(rows, list):
                return
            # Normalizovat: path array → kategorie název
            for row in rows:
                path = row.get("path")
                if isinstance(path, list) and path:
                    row["categoryName"] = " > ".join(str(p) for p in path)
                    row["categoryShortName"] = str(path[-1])
            sorted_rows = sorted(rows, key=lambda x: self._m(x, "clicks"), reverse=True)
            report.top_categories_by_clicks = sorted_rows[:20]
        except Exception as e:
            report.warnings.append(f"stats_category: {e}")

    def _fetch_stats_context(self, report: AnalysisReport):
        data = self._safe("stats_context", report, lambda: self.api.get_stats_context(30))
        if not data:
            return
        try:
            rows = data.get("data", [])
            if not isinstance(rows, list):
                return
            # Každý řádek: device, source, views/clicks/cost/conversions (nested objekty)
            normalized = []
            for row in rows:
                device = row.get("device", "unknown")
                source = row.get("source", "unknown")
                views = self._num(row.get("views", 0))
                clicks = self._num(row.get("clicks", 0))
                cost = self._num(row.get("cost", 0))
                convs = self._num(row.get("conversions", 0))
                conv_value = self._num(row.get("conversionsValue", 0))
                pno = round(cost / conv_value * 100, 2) if conv_value > 0 else None
                avg_pos_search = None
                avg_pos = row.get("avgPosition")
                if isinstance(avg_pos, dict):
                    avg_pos_search = avg_pos.get("search")
                normalized.append({
                    "device": device,
                    "source": source,
                    "views": int(views),
                    "clicks": int(clicks),
                    "cost": round(cost, 2),
                    "conversions": int(convs),
                    "conversionsValue": round(conv_value, 2),
                    "pno": pno,
                    "avgPositionSearch": avg_pos_search,
                })
            report.device_stats = normalized
        except Exception as e:
            report.warnings.append(f"stats_context: {e}")

    # ─────────────────────────────────────────────────────────
    # Fetching – Recenze
    # ─────────────────────────────────────────────────────────

    def _fetch_reviews(self, report: AnalysisReport):
        data = self._safe("reviews", report, self.api.get_reviews)
        if data:
            try:
                rows = data.get("data", [])
                if isinstance(rows, list) and rows:
                    report.reviews_total = data.get("totalCount", len(rows))
                    ratings = []
                    pos = neg = 0
                    normalized_reviews = []
                    for r in rows:
                        # satisfaction.overall: yes | yes_but | no
                        satisfaction = r.get("satisfaction") or {}
                        overall = satisfaction.get("overall") if isinstance(satisfaction, dict) else None
                        # Mapování na numerické hodnocení
                        score = None
                        if overall == "yes":
                            score = 5.0
                            pos += 1
                        elif overall == "yes_but":
                            score = 3.0
                        elif overall == "no":
                            score = 1.0
                            neg += 1
                        if score is not None:
                            ratings.append(score)

                        normalized_reviews.append({
                            "satisfaction": satisfaction,
                            "overall": overall,
                            "score": score,
                            "positiveComment": r.get("positiveComment") or "",
                            "negativeComment": r.get("negativeComment") or "",
                            "userName": r.get("userName") or "Zákazník",
                            "createTimestamp": r.get("createTimestamp"),
                            "orderId": r.get("orderId"),
                        })

                    if ratings:
                        report.reviews_avg_rating = round(sum(ratings) / len(ratings), 2)
                    report.reviews_positive = pos
                    report.reviews_negative = neg
                    report.reviews_list = normalized_reviews[:20]
            except Exception as e:
                report.warnings.append(f"reviews parsing: {e}")

        data2 = self._safe("product_reviews", report, self.api.get_product_reviews)
        if data2:
            try:
                rows2 = data2.get("data", [])
                if isinstance(rows2, list):
                    normalized_prod = []
                    for r in rows2:
                        pd = r.get("productData") or {}
                        normalized_prod.append({
                            "ratingStars": r.get("ratingStars"),
                            "text": r.get("text") or "",
                            "positiveComments": r.get("positiveComments") or "",
                            "negativeComments": r.get("negativeComments") or "",
                            "productName": pd.get("productName") or "",
                            "itemId": pd.get("itemId"),
                        })
                    report.product_reviews_list = normalized_prod[:20]
            except Exception as e:
                report.warnings.append(f"product_reviews parsing: {e}")

    # ─────────────────────────────────────────────────────────
    # Fetching – Parametry kategorií
    # ─────────────────────────────────────────────────────────

    def _fetch_category_params(self, report: AnalysisReport):
        cat_ids = []
        seen = set()
        for item in report.raw_items:
            cid = item.get("categoryId")
            if cid and cid not in seen:
                seen.add(cid)
                cat_ids.append(cid)
            if len(cat_ids) >= 10:
                break

        if not cat_ids:
            return

        data = self._safe("category_params", report, lambda: self.api.get_categories(cat_ids))
        if not data:
            return
        try:
            cats = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(cats, list):
                for cat in cats:
                    cid = str(cat.get("id") or cat.get("categoryId") or "")
                    attrs = cat.get("attributes") or cat.get("params") or cat.get("parameters") or []
                    if cid and attrs:
                        report.category_params[cid] = attrs
            elif isinstance(cats, dict):
                report.category_params = {str(k): v for k, v in cats.items()}
        except Exception as e:
            report.warnings.append(f"category_params: {e}")

    # ─────────────────────────────────────────────────────────
    # Analýza kategorií
    # ─────────────────────────────────────────────────────────

    def _analyze_feed_quality(self, report: AnalysisReport):
        """Analyzuje kvalitu XML feedu – chybějící elementy, doporučení EXTRA_MESSAGE."""
        if not report.feed_items_by_id:
            return

        feed_items = list(report.feed_items_by_id.values())
        total = len(feed_items)

        # Spočítat přítomnost klíčových elementů
        has = {
            "price": 0, "ean": 0, "deliveryDate": 0, "imgUrl": 0,
            "categoryText": 0, "manufacturer": 0, "params": 0,
            "extraMessage": 0, "priceBeforeDiscount": 0, "salesVoucher": 0,
            "warranty": 0, "maxCpc": 0,
        }
        # Cenové pásma pro EXTRA_MESSAGE doporučení
        premium_items = []     # > 2000 Kč – dárkové balení, splátky
        gift_set_items = []    # dárkové sady
        delivery_free = 0

        for fi in feed_items:
            if fi.get("price") is not None: has["price"] += 1
            if fi.get("ean"): has["ean"] += 1
            if fi.get("deliveryDate") is not None: has["deliveryDate"] += 1
            if fi.get("imgUrl"): has["imgUrl"] += 1
            if fi.get("categoryText"): has["categoryText"] += 1
            if fi.get("manufacturer"): has["manufacturer"] += 1
            if fi.get("params"): has["params"] += 1

            price = fi.get("price") or 0
            name = (fi.get("productName") or "").lower()

            if price >= 2000:
                premium_items.append(fi)
            if any(kw in name for kw in ["dárk", "gift", "set ", "sada", "kazeta"]):
                gift_set_items.append(fi)

        # EXTRA_MESSAGE doporučení dle typu produktu
        extra_message_recs = []

        # Doprava zdarma – 100% položek má DELIVERY_PRICE=0
        extra_message_recs.append({
            "message": "free_return",
            "label": "Vrácení s dopravou zdarma",
            "count": total,
            "reason": "Pokud eshop nabízí bezplatné vrácení, zvýší to konverzi u prémiové kosmetiky.",
        })

        if gift_set_items:
            extra_message_recs.append({
                "message": "gift_package",
                "label": "Dárkové balení",
                "count": len(gift_set_items),
                "reason": f"{len(gift_set_items)} produktů jsou dárkové sady/sety – ideální kandidáti.",
            })

        if premium_items:
            extra_message_recs.append({
                "message": "split_payment",
                "label": "Možnost nákupu na splátky",
                "count": len(premium_items),
                "reason": f"{len(premium_items)} produktů stojí nad 2 000 Kč – splátky snižují bariéru nákupu.",
            })

        extra_message_recs.append({
            "message": "voucher",
            "label": "Voucher na další nákup",
            "count": total,
            "reason": "Slevový kód na příští nákup zvyšuje opakované konverze u kosmetiky.",
        })

        extra_message_recs.append({
            "message": "free_gift",
            "label": "Dárek zdarma (vzorky)",
            "count": total,
            "reason": "Vzorky parfémů/kosmetiky k objednávce – běžná praxe, silný konverzní faktor.",
        })

        report.feed_quality = {
            "total": total,
            "has": has,
            "missing_extra_message": total,
            "missing_params": total - has["params"],
            "missing_price_before_discount": total,
            "missing_warranty": total,
            "missing_max_cpc": total,
            "premium_items_count": len(premium_items),
            "gift_set_count": len(gift_set_items),
            "extra_message_recommendations": extra_message_recs,
        }

    def _analyze_categories(self, report: AnalysisReport):
        cat_agg: Dict[str, dict] = defaultdict(lambda: {
            "category": "",
            "categoryId": None,
            "items": 0,
            "paired": 0,
            "shopCounts": [],
            "priceVsMinList": [],
            "suggestedCpcs": [],
            "maxCpcs": [],
            "noDelivery": 0,
            "noParams": 0,
            "noEan": 0,
        })

        for item in report.raw_items:
            cat = item.get("category") or "Bez kategorie"
            cid = item.get("categoryId")
            a = cat_agg[cat]
            a["category"] = cat
            if cid:
                a["categoryId"] = cid
            a["items"] += 1
            if item.get("paired"):
                a["paired"] += 1
            if item.get("shopCount"):
                a["shopCounts"].append(float(item["shopCount"]))
            if item.get("priceVsMin"):
                a["priceVsMinList"].append(float(item["priceVsMin"]))
            if item.get("suggestedCpc"):
                a["suggestedCpcs"].append(float(item["suggestedCpc"]))
            if item.get("maxCpc"):
                a["maxCpcs"].append(float(item["maxCpc"]))
            if not item.get("hasDelivery"):
                a["noDelivery"] += 1
            if not item.get("hasParams"):
                a["noParams"] += 1
            if not item.get("hasEan"):
                a["noEan"] += 1

        # Výkonnostní statistiky z API
        stat_by_cat: Dict[str, dict] = {}
        for row in report.top_categories_by_clicks:
            cat_name = row.get("categoryName") or row.get("categoryShortName") or ""
            cat_id = str(row.get("categoryId") or "")
            key = cat_name or cat_id
            if key:
                stat_by_cat[key] = row
                if cat_id:
                    stat_by_cat[cat_id] = row

        def avg(lst):
            return round(sum(lst) / len(lst), 2) if lst else None

        result = []
        for cat, a in cat_agg.items():
            stats = stat_by_cat.get(cat) or stat_by_cat.get(str(a.get("categoryId") or "")) or {}
            clicks = int(self._m(stats, "clicks"))
            views = int(self._m(stats, "views"))
            cost = self._m(stats, "cost")
            convs = int(self._m(stats, "conversions"))

            avg_shop_count = avg(a["shopCounts"])
            avg_price_ratio = avg(a["priceVsMinList"])
            avg_suggested_cpc = avg(a["suggestedCpcs"])
            avg_max_cpc = avg(a["maxCpcs"])

            cpc_gap = None
            if avg_suggested_cpc and avg_max_cpc:
                cpc_gap = round(avg_suggested_cpc - avg_max_cpc, 2)

            ctr = round(clicks / views * 100, 2) if views > 0 else None

            result.append({
                "category": cat,
                "categoryId": a["categoryId"],
                "items": a["items"],
                "paired": a["paired"],
                "pairedPct": round(a["paired"] / a["items"] * 100) if a["items"] > 0 else 0,
                "avgShopCount": avg_shop_count,
                "avgPriceVsMin": avg_price_ratio,
                "avgSuggestedCpc": avg_suggested_cpc,
                "avgMaxCpc": avg_max_cpc,
                "cpcGap": cpc_gap,
                "noDelivery": a["noDelivery"],
                "noParams": a["noParams"],
                "noEan": a["noEan"],
                "clicks": clicks,
                "views": views,
                "ctr": ctr,
                "cost": round(self._halere(cost, max(clicks, 1)), 2),
                "conversions": convs,
            })

        result.sort(key=lambda x: (-(x["clicks"] or 0), -x["items"]))
        report.categories_analysis = result

        # Souhrnná konkurenční analýza
        all_shop_counts = [item["shopCount"] for item in report.raw_items if item.get("shopCount")]
        all_price_ratios = [item["priceVsMin"] for item in report.raw_items if item.get("priceVsMin")]
        report.competition_summary = {
            "avgShopCount": avg(all_shop_counts),
            "medianShopCount": sorted(all_shop_counts)[len(all_shop_counts)//2] if all_shop_counts else None,
            "maxShopCount": max(all_shop_counts) if all_shop_counts else None,
            "itemsWithCompetition": len(all_shop_counts),
            "avgPriceVsMin": avg(all_price_ratios),
            "priceBetterThan10pct": sum(1 for r in all_price_ratios if r <= 1.0),
            "priceWorseThan10pct": sum(1 for r in all_price_ratios if r > 1.1),
        }

    # ─────────────────────────────────────────────────────────
    # Doporučení – Feed & XML
    # ─────────────────────────────────────────────────────────

    def _build_feed_recommendations(self, report: AnalysisReport):
        recs: List[Recommendation] = []
        total = report.items_total
        errors = report.items_errors
        improvements = report.items_improvements
        paired = report.items_paired

        if errors > 0:
            pct = round(errors / total * 100) if total else 0
            recs.append(Recommendation(
                priority="critical", section="feed_errors",
                title=f"{errors} položek má chyby ve feedu ({pct} %)",
                detail=(
                    "Položky s chybami se vůbec nezobrazují. Zkontrolujte Centrum prodejce → Diagnostika.\n"
                    "Nejčastější příčiny: chybějící povinný prvek, nedostupný obrázek, nesoulad ceny s webem."
                ),
                example=(
                    "<SHOPITEM>\n"
                    "  <ITEM_ID>SKU-001</ITEM_ID>\n"
                    "  <PRODUCTNAME>Samsung Galaxy S24 128GB Black</PRODUCTNAME>\n"
                    "  <DESCRIPTION>Smartphone s 6,2\" AMOLED displejem...</DESCRIPTION>\n"
                    "  <URL>https://shop.cz/samsung-galaxy-s24</URL>\n"
                    "  <IMGURL>https://shop.cz/img/s24.jpg</IMGURL>\n"
                    "  <PRICE_VAT>18990</PRICE_VAT>\n"
                    "  <CATEGORYTEXT>Elektronika | Mobilní telefony | Samsung</CATEGORYTEXT>\n"
                    "</SHOPITEM>"
                ),
                affected=errors,
            ))

        if total > 0 and paired < total:
            unpaired = total - paired
            ratio = round(paired / total * 100)
            recs.append(Recommendation(
                priority="critical" if ratio < 60 else "important",
                section="pairing",
                title=f"{ratio} % položek spárováno ({unpaired} nespárováno)",
                detail=(
                    "Spárované položky se zobrazují s recenzemi, srovnáním cen a jsou lépe dohledatelné.\n"
                    "Párování ovlivňuje hlavně EAN (nejdůležitější), pak MANUFACTURER a PRODUCTNO."
                ),
                example=(
                    "<EAN>3165140892032</EAN>\n"
                    "<MANUFACTURER>Bosch</MANUFACTURER>\n"
                    "<PRODUCTNO>06019H5200</PRODUCTNO>"
                ),
                affected=unpaired,
            ))

        if report.items_no_delivery > 0:
            pct = round(report.items_no_delivery / total * 100) if total else 0
            recs.append(Recommendation(
                priority="important", section="delivery",
                title=f"{report.items_no_delivery} položek ({pct} %) nemá nastavenou dostupnost (DELIVERY_DATE)",
                detail=(
                    "Produkty bez DELIVERY_DATE se zobrazují hůře – algoritmus Zboží.cz upřednostňuje\n"
                    "produkty s jasnou dostupností."
                ),
                example=(
                    "<DELIVERY_DATE>0</DELIVERY_DATE>  <!-- skladem -->\n"
                    "<DELIVERY_DATE>3</DELIVERY_DATE>  <!-- do 3 dní -->"
                ),
                affected=report.items_no_delivery,
            ))

        # EXTRA_MESSAGE doporučení z feed analýzy
        fq = report.feed_quality
        if fq and fq.get("missing_extra_message", 0) > 0:
            em_recs = fq.get("extra_message_recommendations", [])
            em_detail_parts = []
            for em in em_recs:
                em_detail_parts.append(
                    f"• {em['label']} ({em['message']}): {em['count']} položek – {em['reason']}"
                )
            recs.append(Recommendation(
                priority="important", section="extra_message",
                title=f"Žádná položka nemá EXTRA_MESSAGE – přidejte akční štítky",
                detail=(
                    "EXTRA_MESSAGE se zobrazuje přímo ve výpisu na Nákupech a výrazně zvyšuje CTR.\n"
                    "Doporučené akce pro váš sortiment:\n\n" + "\n".join(em_detail_parts)
                ),
                example=(
                    "<EXTRA_MESSAGE>\n"
                    "  <EXTRA_MESSAGE_TYPE>free_gift</EXTRA_MESSAGE_TYPE>\n"
                    "  <EXTRA_MESSAGE_TEXT>Vzorky parfémů zdarma</EXTRA_MESSAGE_TEXT>\n"
                    "</EXTRA_MESSAGE>\n"
                    "<EXTRA_MESSAGE>\n"
                    "  <EXTRA_MESSAGE_TYPE>gift_package</EXTRA_MESSAGE_TYPE>\n"
                    "</EXTRA_MESSAGE>"
                ),
                affected=fq["missing_extra_message"],
            ))

        # PRICE_BEFORE_DISCOUNT
        if fq and fq.get("missing_price_before_discount", 0) > 0:
            recs.append(Recommendation(
                priority="important", section="price_discount",
                title="Žádná položka nemá PRICE_BEFORE_DISCOUNT – zviditelněte slevy",
                detail=(
                    "Pokud eshop nabízí zlevněné produkty, přidejte původní cenu.\n"
                    "Na Nákupech se zobrazí přeškrtnutá cena a procentuální sleva (5–90 %).\n"
                    "To výrazně zvyšuje CTR u slevových položek."
                ),
                example=(
                    "<PRICE_VAT>1290</PRICE_VAT>\n"
                    "<PRICE_BEFORE_DISCOUNT>1590</PRICE_BEFORE_DISCOUNT>"
                ),
                affected=fq["missing_price_before_discount"],
            ))

        # WARRANTY
        if fq and fq.get("missing_warranty", 0) > 0:
            recs.append(Recommendation(
                priority="tip", section="warranty",
                title="Žádná položka nemá WARRANTY – přidejte záruční dobu",
                detail="Záruční doba zvyšuje důvěryhodnost nabídky a může ovlivnit rozhodování zákazníka.",
                example="<WARRANTY>24</WARRANTY>  <!-- měsíce -->",
                affected=fq["missing_warranty"],
            ))

        # MAX_CPC z feedu
        if fq and fq.get("missing_max_cpc", 0) > 0:
            recs.append(Recommendation(
                priority="tip", section="max_cpc_feed",
                title="Žádná položka nemá MAX_CPC – řiďte bidding přímo z feedu",
                detail=(
                    "MAX_CPC a MAX_CPC_SEARCH v feedu umožňují nastavit maximální cenu za proklik\n"
                    "per položku. Můžete tak zvýšit CPC u produktů s vysokou marží a snížit u ztrátových."
                ),
                example=(
                    "<MAX_CPC>3.50</MAX_CPC>\n"
                    "<MAX_CPC_SEARCH>2.80</MAX_CPC_SEARCH>"
                ),
            ))

        if report.items_no_params > 0:
            pct = round(report.items_no_params / total * 100) if total else 0
            top_no_params = sorted(
                [c for c in report.categories_analysis if c.get("noParams", 0) > 0],
                key=lambda x: x["noParams"], reverse=True
            )[:3]
            cat_examples = "\n".join(
                f"  • {c['category']}: {c['noParams']} položek bez parametrů"
                for c in top_no_params
            )
            recs.append(Recommendation(
                priority="important", section="params",
                title=f"{report.items_no_params} položek ({pct} %) nemá žádné parametry (PARAMS)",
                detail=(
                    "Parametry produktu zlepšují filtrování ve výsledcích a párování s katalogem.\n\n"
                    f"Nejpostiženější kategorie:\n{cat_examples}"
                ),
                example=(
                    "<PARAMS>\n"
                    "  <PARAM>\n"
                    "    <PARAM_NAME>Barva</PARAM_NAME>\n"
                    "    <VAL>Černá</VAL>\n"
                    "  </PARAM>\n"
                    "</PARAMS>"
                ),
                affected=report.items_no_params,
            ))

        if report.category_params:
            for cid, attrs in list(report.category_params.items())[:3]:
                attr_names = []
                if isinstance(attrs, list):
                    for a in attrs[:8]:
                        n = a.get("name") or a.get("paramName") or str(a)
                        if n:
                            attr_names.append(n)
                if attr_names:
                    recs.append(Recommendation(
                        priority="tip", section="category_params",
                        title=f"Doporučené parametry pro kategorii ID {cid}",
                        detail="Přidejte tyto parametry dle specifikace Zboží.cz: " + ", ".join(attr_names),
                        example="\n".join(
                            f'<PARAM><PARAM_NAME>{n}</PARAM_NAME><VAL>...</VAL></PARAM>'
                            for n in attr_names[:5]
                        ),
                    ))

        if report.items_no_ean > 0:
            pct = round(report.items_no_ean / total * 100) if total else 0
            recs.append(Recommendation(
                priority="important", section="ean",
                title=f"{report.items_no_ean} položek ({pct} %) nemá EAN",
                detail="EAN je nejdůležitější atribut pro párování s produktovým katalogem.",
                example="<EAN>8806095467825</EAN>",
                affected=report.items_no_ean,
            ))

        cs = report.competition_summary
        if cs.get("priceWorseThan10pct", 0) > 0:
            recs.append(Recommendation(
                priority="important", section="pricing",
                title=f"{cs['priceWorseThan10pct']} položek je o více než 10 % dražších než nejlevnější konkurent",
                detail=(
                    f"Průměrný poměr vaší ceny vůči nejlevnějšímu: "
                    f"{cs.get('avgPriceVsMin', '—')}"
                ),
                affected=cs["priceWorseThan10pct"],
            ))

        recs.append(Recommendation(
            priority="important", section="product_names",
            title="Názvy produktů nesmí obsahovat propagační text",
            detail="PRODUCTNAME: bez 'akce', 'výprodej', 'sleva'. Formát: [Značka] [Model] [Klíčová spec].",
            example=(
                "<!-- SPRÁVNĚ -->\n<PRODUCTNAME>Adidas Runfalcon 3.0 W Black EU 39</PRODUCTNAME>\n"
                "<!-- ŠPATNĚ -->\n<!-- <PRODUCTNAME>AKCE! Adidas -30% VÝPRODEJ</PRODUCTNAME> -->"
            ),
        ))

        recs.append(Recommendation(
            priority="important", section="images",
            title="Obrázky: min. 100x100 px, doporučeno 600x600 px+, HTTPS",
            detail="Bílé/průhledné pozadí, bez vodoznaků. IMGURL_ALTERNATIVE pro galerii.",
            example=(
                "<IMGURL>https://shop.cz/img/produkt-600x600.jpg</IMGURL>\n"
                "<IMGURL_ALTERNATIVE>https://shop.cz/img/detail.jpg</IMGURL_ALTERNATIVE>"
            ),
        ))

        if improvements > 0:
            recs.append(Recommendation(
                priority="tip", section="improvements",
                title=f"{improvements} položek lze zlepšit (z diagnostics API)",
                detail="Přidejte chybějící atributy dle Centrum prodejce → Diagnostika → Lze zlepšit.",
                affected=improvements,
            ))

        report.feed_recommendations = recs

    # ─────────────────────────────────────────────────────────
    # Doporučení – Sklik Nákupy
    # ─────────────────────────────────────────────────────────

    def _build_sklik_recommendations(self, report: AnalysisReport):
        recs: List[Recommendation] = []

        cost = report.perf_cost
        clicks = report.perf_clicks
        convs = report.perf_conversions
        cats = report.categories_analysis

        underbid = sorted(
            [c for c in cats if c.get("cpcGap") and c["cpcGap"] > 0.5 and c.get("clicks", 0) > 0],
            key=lambda x: x["cpcGap"], reverse=True
        )[:5]

        strong_cats = [c for c in cats if c.get("ctr") and c["ctr"] >= 2.0 and c.get("clicks", 0) > 5]
        weak_cats = [c for c in cats if c.get("ctr") and c["ctr"] < 0.5 and c.get("clicks", 0) > 0]

        recs.append(Recommendation(
            priority="important", section="setup",
            title="Propojení Zboží.cz se Sklikem – krok za krokem",
            detail=(
                "1. Centrum prodejce (zbozi.cz) → Nastavení → Sklik → Propojit účet\n"
                "2. Sklik.cz → Nová kampaň → Nákupy → vyberte provozovnu\n"
                "3. Geografické cílení: Česká republika\n"
                "4. Vytvořte skupiny produktů dle kategorií\n"
                "5. Nastavte CPC nabídky per skupina"
            ),
        ))

        if underbid:
            lines = [f"  • {c['category']}: doporučeno {c.get('avgSuggestedCpc','—')} Kč, nastaveno {c.get('avgMaxCpc','—')} Kč (gap +{c['cpcGap']} Kč)" for c in underbid]
            recs.append(Recommendation(
                priority="critical", section="cpc_gap",
                title=f"V {len(underbid)} kategoriích nabízíte méně CPC než API doporučuje",
                detail="Nízké CPC = ztráta zobrazení v Nákupech. Navyšte nabídky:\n" + "\n".join(lines),
                affected=sum(c.get("items", 0) for c in underbid),
            ))

        if strong_cats:
            lines = [f"  • {c['category']}: CTR {c['ctr']} %, {c['clicks']} kliknutí, {c.get('conversions',0)} konverzí" for c in strong_cats[:5]]
            recs.append(Recommendation(
                priority="important", section="strong_cats",
                title=f"{len(strong_cats)} silných kategorií (CTR >= 2 %) – zvyšte rozpočet",
                detail="Tyto kategorie fungují nejlépe:\n" + "\n".join(lines),
            ))

        if weak_cats:
            lines = [f"  • {c['category']}: CTR {c['ctr']} %, {c['clicks']} kliknutí" for c in weak_cats[:5]]
            recs.append(Recommendation(
                priority="important", section="weak_cats",
                title=f"{len(weak_cats)} slabých kategorií (CTR < 0.5 %) – optimalizujte nebo pozastavte",
                detail="Slabé kategorie:\n" + "\n".join(lines),
                affected=sum(c.get("items", 0) for c in weak_cats),
            ))

        high_comp = [c for c in cats if c.get("avgShopCount") and c["avgShopCount"] > 15 and c.get("clicks", 0) > 0]
        if high_comp:
            lines = [f"  • {c['category']}: průměrně {c['avgShopCount']:.0f} eshopů na kartě" for c in high_comp[:4]]
            recs.append(Recommendation(
                priority="important", section="competition",
                title=f"{len(high_comp)} kategorií s vysokou konkurencí (15+ eshopů na kartě)",
                detail="Vysoká konkurence vyžaduje cenovou konkurenceschopnost a vyšší CPC.\n" + "\n".join(lines),
            ))

        cs = report.competition_summary
        avg_ratio = cs.get("avgPriceVsMin")
        if avg_ratio and avg_ratio > 1.05:
            recs.append(Recommendation(
                priority="important", section="pricing",
                title=f"Průměrně jste o {round((avg_ratio-1)*100, 1)} % dražší než nejlevnější konkurent",
                detail=(
                    f"Průměrný poměr vaší ceny / nejlevnější ceny: {avg_ratio}\n"
                    f"Položky s nejlepší cenou: {cs.get('priceBetterThan10pct', 0)}\n"
                    f"Položky o 10 %+ dražší: {cs.get('priceWorseThan10pct', 0)}"
                ),
            ))

        if cost > 0:
            daily = round(cost / 30, 0)
            recs.append(Recommendation(
                priority="important", section="budget",
                title=f"Denní výdaje: průměr {daily:,.0f} Kč",
                detail=f"Nastavte +30 % rezervu nad průměrem. Sledujte Impression Share.",
            ))

        if convs == 0:
            recs.append(Recommendation(
                priority="critical", section="tracking",
                title="Sledování konverzí není nastaveno – bez toho nelze optimalizovat",
                detail=(
                    "1. Sklik → Nástroje → Konverzní akce → Nová akce\n"
                    "2. Vložte kód na stránku 'Děkujeme za objednávku'\n"
                    "3. Alternativa: import konverzí z Google Analytics / GA4"
                ),
            ))
        elif convs < 30:
            recs.append(Recommendation(
                priority="important", section="tracking",
                title=f"Pouze {convs} konverzí za 30 dní – nedostatek dat pro automatické strategie",
                detail="Pro Cílové ROAS potřebujete min. 30 konverzí/měsíc.",
            ))

        devs = report.device_stats
        if devs:
            lines = []
            for d in devs:
                dev = d.get("device", "?")
                src = d.get("source", "?")
                cl = d.get("clicks", 0)
                cv = d.get("conversions", 0)
                co = d.get("cost", 0)
                lines.append(f"  • {dev}/{src}: {cl:,} kliknutí | {cv} konverzí | {round(co):,} Kč")
            recs.append(Recommendation(
                priority="tip", section="devices",
                title="Optimalizace nabídek dle zařízení a zdroje",
                detail="\n".join(lines[:8]),
            ))

        recs.append(Recommendation(
            priority="tip", section="negatives",
            title="Negativní klíčová slova pro Nákupy",
            detail=(
                "Sledujte záložku Vyhledávací dotazy v Skliku a přidávejte:\n"
                "  bazar, použitý, second hand | zdarma, gratis | návod, recenze, test"
            ),
        ))

        report.sklik_recommendations = recs
