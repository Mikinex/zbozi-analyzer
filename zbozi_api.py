import base64
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import requests


class RateLimiter:
    def __init__(self, min_interval_seconds: float):
        self.min_interval = min_interval_seconds
        self.last_call = 0.0

    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


class ZboziAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ZboziAPI:
    BASE_URL = "https://api.zbozi.cz"

    def __init__(self, shop_id: str, api_key: str):
        self.shop_id = shop_id
        credentials = f"{shop_id}:{api_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
        })
        # Konzervativní globální rate limit – 2 s mezi požadavky
        self._rl = RateLimiter(2.0)

    def _get(self, endpoint: str, params: Dict = None) -> Any:
        self._rl.wait()
        url = f"{self.BASE_URL}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            raise ZboziAPIError(f"Síťová chyba: {e}")

        if resp.status_code == 401:
            raise ZboziAPIError("Neplatné přihlašovací údaje (ID provozovny nebo API klíč)", 401)
        if resp.status_code == 403:
            raise ZboziAPIError("Přístup zakázán – zkontrolujte oprávnění API klíče", 403)
        if resp.status_code == 404:
            raise ZboziAPIError(f"Endpoint nenalezen: {endpoint}", 404)
        if resp.status_code == 429:
            raise ZboziAPIError("Rate limit – zkuste znovu za chvíli", 429)
        if resp.status_code >= 500:
            raise ZboziAPIError(f"Chyba serveru Zboží.cz ({resp.status_code})", resp.status_code)
        if not resp.ok:
            raise ZboziAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code)

        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    # ── Diagnostika ──────────────────────────────────────────────────
    def get_diagnostics(self) -> Any:
        return self._get("/v1/shop/diagnostics/item")

    def get_diagnostics_detail(self, status: str = None, limit: int = 100) -> Any:
        """Detail diagnostiky s možností filtrovat dle statusu."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        return self._get("/v1/shop/diagnostics/item", params)

    # ── Položky ─────────────────────────────────────────────────────
    def get_items(self, limit: int = 3000, offset: int = 0,
                  load_product_detail: bool = True,
                  load_search_info: bool = True) -> Any:
        """Stáhne položky. S loadProductDetail max 30, s loadSearchInfo max 300."""
        params = {"offset": offset}
        if load_product_detail:
            params["loadProductDetail"] = True
            params["limit"] = min(limit, 30)
        elif load_search_info:
            params["loadSearchInfo"] = True
            params["limit"] = min(limit, 300)
        else:
            params["limit"] = min(limit, 3000)
        if load_search_info and load_product_detail:
            # Oba najednou – limit je 30 (přísnější)
            params["loadSearchInfo"] = True
        return self._get("/v1/shop/items", params)

    def get_items_basic(self, limit: int = 3000, offset: int = 0) -> Any:
        """Položky bez detailů – limit až 3000."""
        return self._get("/v1/shop/items", {
            "limit": min(limit, 3000),
            "offset": offset,
        })

    # ── Kampaň ───────────────────────────────────────────────────────
    def get_campaign(self) -> Any:
        return self._get("/v1/shop/campaign/current")

    # ── Feedy ────────────────────────────────────────────────────────
    def get_feeds(self) -> Any:
        return self._get("/v1/shop/feeds")

    # ── Bidding info ──────────────────────────────────────────────────
    def get_bidding_info(self) -> Any:
        return self._get("/v1/shop/bidding-info")

    # ── Statistiky ───────────────────────────────────────────────────
    def get_stats_aggregated(self, days: int = 30) -> Any:
        ts_to = int(datetime.now().timestamp())
        ts_from = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._get("/v1/shop/statistics/aggregated", {
            "timestampFrom": ts_from,
            "timestampTo": ts_to,
            "granularity": "daily",
        })

    def get_stats_category(self, days: int = 30) -> Any:
        ts_to = int(datetime.now().timestamp())
        ts_from = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._get("/v1/shop/statistics/category", {
            "timestampFrom": ts_from,
            "timestampTo": ts_to,
        })

    def get_stats_context(self, days: int = 30) -> Any:
        ts_to = int(datetime.now().timestamp())
        ts_from = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._get("/v1/shop/statistics/context", {
            "timestampFrom": ts_from,
            "timestampTo": ts_to,
        })

    # ── Recenze ───────────────────────────────────────────────────────
    def get_reviews(self, limit: int = 100, days: int = 30) -> Any:
        ts_from = int((datetime.now() - timedelta(days=min(days, 180))).timestamp())
        return self._get("/v1/shop/reviews", {
            "timestampFrom": ts_from,
            "limit": limit,
            "offset": 0,
        })

    def get_product_reviews(self, limit: int = 100, days: int = 30) -> Any:
        # Oprava: přidán parametr "offset": 0 (konzistentní s get_reviews).
        # Endpoint /v1/shop/product-reviews nemusí být dostupný pro všechny provozovny.
        ts_from = int((datetime.now() - timedelta(days=min(days, 180))).timestamp())
        return self._get("/v1/shop/product-reviews", {
            "timestampFrom": ts_from,
            "limit": limit,
            "offset": 0,
        })

    # ── Produkty (konkurenční data) ──────────────────────────────────
    def get_products(self, product_ids: list) -> Any:
        """Vrátí shopCount, minPrice, maxPrice, shopItems pro produkty (max 10 IDs)."""
        ids_str = ",".join(str(i) for i in product_ids[:10])
        return self._get(f"/v1/products/{ids_str}")

    # ── Kategorie (atributy/parametry) ───────────────────────────────
    def get_categories(self, category_ids: list) -> Any:
        """Vrátí atributy (parametry) pro zadané kategorie."""
        ids_str = ",".join(str(i) for i in category_ids[:10])
        return self._get(f"/v1/categories/{ids_str}")

    def get_categories_tree(self) -> Any:
        """Vrátí strom kategorií."""
        return self._get("/v1/categories/tree")

    # ── Manufacturers ──────────────────────────────────────────────────
    def get_manufacturers(self) -> Any:
        return self._get("/v1/manufacturers")

    def get_manufacturers_search(self, query: str) -> Any:
        return self._get("/v1/manufacturers/search", {"query": query})

    def get_manufacturers_by_ids(self, ids: list) -> Any:
        ids_str = ",".join(str(i) for i in ids[:10])
        return self._get(f"/v1/manufacturers/{ids_str}")

    # ── Shops ──────────────────────────────────────────────────────────
    def get_shops(self, shop_ids: list) -> Any:
        ids_str = ",".join(str(i) for i in shop_ids[:10])
        return self._get(f"/v1/shops/{ids_str}")

    # ── Item statistics ────────────────────────────────────────────────
    def get_stats_item_list(self) -> Any:
        """Seznam požadavků na statistiky položek."""
        return self._get("/v1/shop/statistics/item")

    def get_stats_item_json(self) -> Any:
        """Statistiky položek (JSON)."""
        return self._get("/v1/shop/statistics/item/json")

    # ── Feed download & parse ──────────────────────────────────────────
    def download_feed(self, feed_url: str, timeout: int = 60) -> List[Dict]:
        """Stáhne XML feed a vrátí seznam položek s klíčovými elementy."""
        if not feed_url:
            raise ZboziAPIError("Feed URL je prázdné")
        try:
            resp = requests.get(feed_url, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ZboziAPIError(f"Nelze stáhnout feed: {e}")

        items = []
        try:
            root = ET.fromstring(resp.content)
            for elem in root.iter():
                # Porovnání bez namespace a case-insensitive
                local = self._local_tag(elem.tag)
                if local == "shopitem":
                    item = self._parse_shopitem(elem)
                    if item:
                        items.append(item)
        except ET.ParseError as e:
            raise ZboziAPIError(f"Chyba parsování XML feedu: {e}")

        return items

    @staticmethod
    def _local_tag(tag: str) -> str:
        """Odstraní XML namespace a vrátí lowercase tag."""
        if not tag:
            return ""
        # {http://namespace}TagName → TagName
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        return tag.lower()

    @classmethod
    def _parse_shopitem(cls, elem) -> Optional[Dict]:
        """Extrahuje klíčové elementy z SHOPITEM."""
        # Sestavit mapu tag → text pro přímé potomky
        # Oprava: <PARAM> elementy jsou uvnitř <PARAMS>, ne přímí potomci <SHOPITEM>.
        # Původní kód hledal local == "param" přímo v potomcích SHOPITEM, ale ty jsou
        # zabaleny ve <PARAMS> obalovacím elementu – proto params bylo vždy prázdné.
        children = {}
        params_elems = []
        for child in elem:
            local = cls._local_tag(child.tag)
            if local == "params":
                # Správně: <PARAMS> obsahuje vnořené <PARAM> elementy
                for param_child in child:
                    if cls._local_tag(param_child.tag) == "param":
                        params_elems.append(param_child)
            elif local == "param":
                # Fallback: někdy může být <PARAM> přímo pod <SHOPITEM>
                params_elems.append(child)
            elif local not in children:
                children[local] = (child.text or "").strip() if child.text else None

        item_id = children.get("item_id")
        if not item_id:
            return None

        # Parametry
        params = []
        for pe in params_elems:
            pname = None
            pval = None
            for sub in pe:
                sl = cls._local_tag(sub.tag)
                if sl == "param_name":
                    pname = (sub.text or "").strip()
                elif sl == "val":
                    pval = (sub.text or "").strip()
            if pname:
                params.append({"name": pname, "value": pval or ""})

        price_str = children.get("price_vat")
        price = None
        if price_str:
            try:
                price = float(price_str.replace(",", ".").replace(" ", ""))
            except ValueError:
                pass

        return {
            "itemId": item_id,
            "price": price,
            "deliveryDate": children.get("delivery_date"),
            "ean": children.get("ean"),
            "url": children.get("url"),
            "imgUrl": children.get("imgurl"),
            "productName": children.get("productname"),
            "manufacturer": children.get("manufacturer"),
            "categoryText": children.get("categorytext"),
            "params": params,
        }
