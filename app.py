import csv
import dataclasses
import io
import json
import math
import traceback

from flask import Flask, render_template, request, jsonify, Response

from zbozi_api import ZboziAPI, ZboziAPIError
from analyzer import ZboziAnalyzer

app = Flask(__name__)
app.config["JSON_ENSURE_ASCII"] = False


def _safe_value(v):
    """Convert non-JSON-serializable floats to None."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _to_dict(obj):
    """Recursively convert dataclasses / dicts to plain JSON-safe dicts."""
    if dataclasses.is_dataclass(obj):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, float):
        return _safe_value(obj)
    # Convert any other non-serializable type to string
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    body = request.get_json(silent=True) or {}
    shop_id = (body.get("shop_id") or "").strip()
    api_key = (body.get("api_key") or "").strip()

    if not shop_id or not api_key:
        return jsonify({"error": "Zadejte ID provozovny a API klíč."}), 400

    try:
        api = ZboziAPI(shop_id, api_key)
        analyzer = ZboziAnalyzer(api)
        skip_feed = body.get("skip_feed", False)
        report = analyzer.analyze(shop_id, skip_feed=skip_feed)

        # If authentication failed entirely, the diagnostics endpoint_status will say so
        diag_status = report.endpoint_status.get("diagnostics", "")
        if "401" in diag_status or "Neplatné" in diag_status or "Unauthorized" in diag_status:
            return jsonify({"error": f"Neplatné přihlašovací údaje: {diag_status}"}), 401

        # feed_items_by_id je interní – neposílat klientovi
        report.feed_items_by_id = {}
        result = _to_dict(report)
        return app.response_class(
            response=json.dumps(result, ensure_ascii=False),
            mimetype="application/json",
        )
    except ZboziAPIError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify({
            "error": "Neočekávaná chyba serveru.",
            "trace": tb,
        }), 500


@app.route("/api/call", methods=["POST"])
def api_call():
    body = request.get_json(silent=True) or {}
    shop_id = (body.get("shop_id") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    endpoint = (body.get("endpoint") or "").strip()
    params = body.get("params") or {}

    if not shop_id or not api_key:
        return jsonify({"error": "Zadejte ID provozovny a API klíč."}), 400
    if not endpoint:
        return jsonify({"error": "Zadejte endpoint."}), 400

    try:
        api = ZboziAPI(shop_id, api_key)

        endpoint_map = {
            "diagnostics": lambda: api.get_diagnostics(),
            "items": lambda: api.get_items(
                limit=int(params.get("limit", 30)),
                offset=int(params.get("offset", 0)),
                load_product_detail=bool(params.get("loadProductDetail", True)),
                load_search_info=bool(params.get("loadSearchInfo", True)),
            ),
            "items_basic": lambda: api.get_items_basic(
                limit=int(params.get("limit", 100)),
                offset=int(params.get("offset", 0)),
            ),
            "feeds": lambda: api.get_feeds(),
            "feed_download": lambda: api.download_feed(
                params.get("feed_url", ""),
            ),
            "campaign": lambda: api.get_campaign(),
            "bidding": lambda: api.get_bidding_info(),
            "stats_aggregated": lambda: api.get_stats_aggregated(
                days=int(params.get("days", 30)),
            ),
            "stats_category": lambda: api.get_stats_category(
                days=int(params.get("days", 30)),
            ),
            "stats_context": lambda: api.get_stats_context(
                days=int(params.get("days", 30)),
            ),
            "stats_item_list": lambda: api.get_stats_item_list(),
            "stats_item_json": lambda: api.get_stats_item_json(),
            "reviews": lambda: api.get_reviews(
                limit=int(params.get("limit", 100)),
                days=int(params.get("days", 30)),
            ),
            "product_reviews": lambda: api.get_product_reviews(
                limit=int(params.get("limit", 100)),
                days=int(params.get("days", 30)),
            ),
            "products": lambda: api.get_products(
                params.get("product_ids", []),
            ),
            "categories": lambda: api.get_categories(
                params.get("category_ids", []),
            ),
            "categories_tree": lambda: api.get_categories_tree(),
            "manufacturers": lambda: api.get_manufacturers(),
            "manufacturers_search": lambda: api.get_manufacturers_search(
                params.get("query", ""),
            ),
            "manufacturers_by_ids": lambda: api.get_manufacturers_by_ids(
                params.get("manufacturer_ids", []),
            ),
            "shops": lambda: api.get_shops(
                params.get("shop_ids", []),
            ),
        }

        if endpoint not in endpoint_map:
            return jsonify({"error": f"Neznámý endpoint: {endpoint}"}), 400

        result = endpoint_map[endpoint]()
        return app.response_class(
            response=json.dumps(result, ensure_ascii=False, default=str),
            mimetype="application/json",
        )
    except ZboziAPIError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify({"error": "Chyba při volání API.", "trace": tb}), 500


@app.route("/export/csv", methods=["POST"])
def export_csv():
    """Export dat jako CSV soubor."""
    body = request.get_json(silent=True) or {}
    data_type = body.get("type", "items")  # items | stats | categories | feed
    rows = body.get("data", [])

    if not rows:
        return jsonify({"error": "Žádná data k exportu"}), 400

    output = io.StringIO()
    if rows:
        # Hlavičky z klíčů prvního řádku
        keys = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Flatten nested values
            flat = {}
            for k in keys:
                v = row.get(k)
                if isinstance(v, (list, dict)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
                else:
                    flat[k] = v
            writer.writerow(flat)

    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=zbozi_{data_type}.csv"},
    )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5055))
    app.run(debug=os.environ.get("RAILWAY_ENVIRONMENT") is None, port=port, host="0.0.0.0")
