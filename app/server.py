#!/usr/bin/env python3
"""RJM Commerce - internal Amazon UK dashboard.

Run:  python3 server.py   (or double-click start.command on the Mac)
Then open http://127.0.0.1:8765

Only listens on this computer (127.0.0.1). Uses sample data until SP-API keys
are stored in the macOS Keychain with setup_keys.command.
"""
import csv
import datetime as dt
import json
import os
import re
import sys
import threading
import time
import traceback
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import spapi
import sample_data

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
STATIC_DIR = os.path.join(HERE, "static")
CONFIG_PATH = os.path.join(HERE, "config.json")
COSTS_PATH = os.path.join(HERE, "costs.csv")
ORDER_ITEMS_CACHE = os.path.join(DATA_DIR, "order_items.json")
PORT = int(os.environ.get("RJM_PORT", "8765"))
CACHE_SECONDS = 600

os.makedirs(DATA_DIR, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

_lock = threading.Lock()
_cache = {}
LAST_HIT = [time.time()]
IDLE_MINUTES = int(os.environ.get("RJM_IDLE_MINUTES", "30"))


def get_client():
    if os.environ.get("RJM_FORCE_SAMPLE") == "1":
        return sample_data.SampleClient(), "sample"
    creds = spapi.load_credentials()
    if creds:
        return spapi.SpApiClient(creds, CONFIG["seller_id"], CONFIG["marketplace_id"]), "live"
    return sample_data.SampleClient(), "sample"


CLIENT, MODE = get_client()


def cached(key, fn, refresh=False):
    with _lock:
        hit = _cache.get(key)
        if hit and not refresh and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    val = fn()
    val["_fetched"] = dt.datetime.now().strftime("%H:%M")
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def iso_days_ago(days):
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def money(x):
    try:
        return float((x or {}).get("CurrencyAmount", (x or {}).get("Amount", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


def load_costs():
    costs = dict(sample_data.SAMPLE_COSTS) if MODE == "sample" else {}
    if os.path.exists(COSTS_PATH):
        with open(COSTS_PATH, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                sku = (row.get("sku") or "").strip()
                val = (row.get("unit_cost_ex_vat") or "").strip().replace("£", "")
                if sku and val:
                    try:
                        costs[sku] = float(val)
                    except ValueError:
                        pass
    return costs


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
REASON_LABEL = {
    "APPROVAL_REQUIRED": "Approval required",
    "ASIN_NOT_FOUND": "ASIN not found",
    "NOT_ELIGIBLE": "Not eligible",
}


def check_eligibility(raw_items):
    results = []
    for raw in raw_items[:50]:
        code = raw.strip().upper().replace(" ", "")
        if not code:
            continue
        row = {"input": code, "asin": None, "title": None, "brand": None,
               "status": None, "reason": "", "link": None}
        try:
            if code.isdigit() and len(code) in (12, 13, 14):
                item = CLIENT.catalog_by_ean(code.zfill(13) if len(code) == 12 else code)
                if not item:
                    row.update(status="Not on Amazon UK", reason="No ASIN matches this barcode")
                    results.append(row)
                    continue
                row["asin"] = item["asin"]
                summ = (item.get("summaries") or [{}])[0]
            elif ASIN_RE.match(code):
                row["asin"] = code
                item = CLIENT.catalog_item(code)
                if not item:
                    row.update(status="ASIN not found", reason="Not in the UK catalogue")
                    results.append(row)
                    continue
                summ = (item.get("summaries") or [{}])[0]
            else:
                row.update(status="Invalid", reason="Enter a 10-character ASIN or a 12/13-digit barcode")
                results.append(row)
                continue
            row["title"] = summ.get("itemName")
            row["brand"] = summ.get("brand")
            r = CLIENT.restrictions(row["asin"])
            reasons = [x for res in r.get("restrictions", []) for x in res.get("reasons", [])]
            if not reasons:
                row["status"] = "Eligible"
            else:
                first = reasons[0]
                row["status"] = REASON_LABEL.get(first.get("reasonCode"), first.get("reasonCode") or "Restricted")
                row["reason"] = " ".join(x.get("message", "") for x in reasons).strip()
                links = [l for x in reasons for l in (x.get("links") or [])]
                if links:
                    row["link"] = links[0].get("resource")
                elif first.get("reasonCode") == "APPROVAL_REQUIRED":
                    row["link"] = ("https://sellercentral.amazon.co.uk/hz/approvalrequest/restrictions/approve?asin="
                                   + row["asin"])
        except spapi.SpApiError as e:
            row.update(status="Error", reason=e.message[:200])
        results.append(row)
        if MODE == "live":
            time.sleep(0.25)
    return {"results": results}


# ---------------------------------------------------------------------------
# Sales & orders
# ---------------------------------------------------------------------------
def _load_item_cache():
    if os.path.exists(ORDER_ITEMS_CACHE):
        try:
            with open(ORDER_ITEMS_CACHE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_item_cache(c):
    tmp = ORDER_ITEMS_CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.replace(tmp, ORDER_ITEMS_CACHE)


def fetch_orders_with_items(days):
    orders = CLIENT.orders(iso_days_ago(days))
    item_cache = _load_item_cache() if MODE == "live" else {}
    changed = False
    for o in orders:
        oid = o["AmazonOrderId"]
        if oid in item_cache:
            o["_items"] = item_cache[oid]
            continue
        items = CLIENT.order_items(oid)
        slim = [{"SellerSKU": i.get("SellerSKU"), "ASIN": i.get("ASIN"), "Title": i.get("Title"),
                 "QuantityOrdered": i.get("QuantityOrdered", 0),
                 "ItemPrice": money(i.get("ItemPrice"))} for i in items]
        o["_items"] = slim
        if MODE == "live":
            if o.get("OrderStatus") in ("Shipped", "Canceled"):
                item_cache[oid] = slim
                changed = True
            time.sleep(2.1)  # getOrderItems is limited to ~0.5 requests/second
    if changed:
        _save_item_cache(item_cache)
    return orders


def build_sales(days):
    orders = fetch_orders_with_items(days)
    start = (dt.datetime.now() - dt.timedelta(days=days - 1)).date()
    daily = {(start + dt.timedelta(days=i)).isoformat(): {"units": 0, "revenue": 0.0, "orders": 0}
             for i in range(days)}
    by_sku = defaultdict(lambda: {"sku": "", "asin": "", "title": "", "units": 0, "revenue": 0.0, "orders": 0})
    recent = []
    for o in sorted(orders, key=lambda x: x.get("PurchaseDate", ""), reverse=True):
        status = o.get("OrderStatus", "")
        day = (o.get("PurchaseDate") or "")[:10]
        units = sum(int(i.get("QuantityOrdered") or 0) for i in o["_items"])
        total = float((o.get("OrderTotal") or {}).get("Amount") or 0)
        if not total:
            total = sum(float(i.get("ItemPrice") or 0) for i in o["_items"])
        if len(recent) < 200:
            recent.append({"id": o["AmazonOrderId"], "date": o.get("PurchaseDate", "")[:16].replace("T", " "),
                           "status": status, "channel": "FBA" if o.get("FulfillmentChannel") == "AFN" else "Merchant",
                           "skus": ", ".join(sorted({i.get("SellerSKU") or "" for i in o["_items"]})),
                           "units": units, "total": round(total, 2)})
        if status == "Canceled":
            continue
        if day in daily:
            daily[day]["units"] += units
            daily[day]["revenue"] += total
            daily[day]["orders"] += 1
        for i in o["_items"]:
            s = by_sku[i.get("SellerSKU") or "?"]
            s["sku"] = i.get("SellerSKU") or "?"
            s["asin"] = i.get("ASIN") or ""
            s["title"] = i.get("Title") or ""
            s["units"] += int(i.get("QuantityOrdered") or 0)
            s["revenue"] += float(i.get("ItemPrice") or 0)
            s["orders"] += 1
    daily_list = [{"date": d, "units": v["units"], "revenue": round(v["revenue"], 2), "orders": v["orders"]}
                  for d, v in sorted(daily.items())]
    skus = sorted(by_sku.values(), key=lambda s: -s["revenue"])
    for s in skus:
        s["revenue"] = round(s["revenue"], 2)
    tot_rev = sum(d["revenue"] for d in daily_list)
    tot_units = sum(d["units"] for d in daily_list)
    tot_orders = sum(d["orders"] for d in daily_list)
    return {"days": days, "daily": daily_list, "by_sku": skus, "orders": recent,
            "totals": {"revenue": round(tot_rev, 2), "units": tot_units, "orders": tot_orders,
                       "avg_order": round(tot_rev / tot_orders, 2) if tot_orders else 0,
                       "pending": sum(1 for o in orders if o.get("OrderStatus") in ("Pending", "Unshipped"))}}


# ---------------------------------------------------------------------------
# Stock & inbound
# ---------------------------------------------------------------------------
def build_stock(refresh=False):
    sales30 = cached("sales:30", lambda: build_sales(30), refresh)
    sold = {s["sku"]: s["units"] for s in sales30["by_sku"]}
    rows = []
    for inv in CLIENT.inventory_summaries():
        d = inv.get("inventoryDetails") or {}
        sku = inv.get("sellerSku")
        fulfillable = int(d.get("fulfillableQuantity") or 0)
        inbound = sum(int(d.get(k) or 0) for k in
                      ("inboundWorkingQuantity", "inboundShippedQuantity", "inboundReceivingQuantity"))
        reserved = int((d.get("reservedQuantity") or {}).get("totalReservedQuantity") or 0)
        unful = int((d.get("unfulfillableQuantity") or {}).get("totalUnfulfillableQuantity") or 0)
        s30 = sold.get(sku, 0)
        per_day = s30 / 30.0
        cover = round(fulfillable / per_day) if per_day > 0 else None
        if fulfillable == 0 and inbound == 0 and s30 > 0:
            alert = "Out of stock"
        elif fulfillable == 0 and inbound > 0:
            alert = "Awaiting inbound"
        elif cover is not None and cover < 21:
            alert = "Reorder soon"
        else:
            alert = ""
        rows.append({"sku": sku, "asin": inv.get("asin"), "fnsku": inv.get("fnSku"),
                     "name": inv.get("productName"), "fulfillable": fulfillable, "inbound": inbound,
                     "reserved": reserved, "unfulfillable": unful,
                     "sold30": s30, "per_week": round(per_day * 7, 1), "cover_days": cover, "alert": alert})
    order = {"Out of stock": 0, "Reorder soon": 1, "Awaiting inbound": 2, "": 3}
    rows.sort(key=lambda r: (order.get(r["alert"], 3), -(r["sold30"] or 0)))

    shipments = []
    try:
        for sh in CLIENT.inbound_shipments():
            if sh.get("ShipmentStatus") in ("CLOSED", "CANCELLED", "DELETED"):
                continue
            items = CLIENT.inbound_items(sh["ShipmentId"])
            if MODE == "live":
                time.sleep(0.6)
            shipped = sum(int(i.get("QuantityShipped") or 0) for i in items)
            received = sum(int(i.get("QuantityReceived") or 0) for i in items)
            shipments.append({"id": sh["ShipmentId"], "name": sh.get("ShipmentName"),
                              "fc": sh.get("DestinationFulfillmentCenterId"), "status": sh.get("ShipmentStatus"),
                              "lines": len(items), "shipped": shipped, "received": received})
        ship_err = None
    except spapi.SpApiError as e:
        ship_err = e.message
    return {"rows": rows, "shipments": shipments, "shipments_error": ship_err,
            "totals": {"skus": len(rows), "fulfillable": sum(r["fulfillable"] for r in rows),
                       "inbound": sum(r["inbound"] for r in rows),
                       "alerts": sum(1 for r in rows if r["alert"] in ("Out of stock", "Reorder soon"))}}


# ---------------------------------------------------------------------------
# Fees & profit
# ---------------------------------------------------------------------------
FEE_LABELS = {
    "Commission": "Referral fee", "FBAPerUnitFulfillmentFee": "FBA fulfilment fee",
    "FBAStorageFee": "FBA storage", "Subscription": "Selling plan", "RefundCommission": "Refund admin fee",
    "FBAInboundTransportationFee": "Inbound carrier", "DigitalServicesFee": "Digital services fee",
    "FixedClosingFee": "Closing fee", "VariableClosingFee": "Closing fee",
}


def _is_tax(charge_type):
    return "Tax" in (charge_type or "") or "VAT" in (charge_type or "")


def build_finance(days):
    ev = CLIENT.financial_events(iso_days_ago(days))
    costs = load_costs()
    sku = defaultdict(lambda: {"sku": "", "units": 0, "refund_units": 0, "sales_net": 0.0, "vat": 0.0,
                               "fees": 0.0, "refunds_net": 0.0, "refund_vat": 0.0, "refund_fees": 0.0})
    fee_types = defaultdict(float)
    promos = 0.0

    for e in ev.get("ShipmentEventList", []):
        for it in e.get("ShipmentItemList") or []:
            s = sku[it.get("SellerSKU") or "?"]
            s["sku"] = it.get("SellerSKU") or "?"
            s["units"] += int(it.get("QuantityShipped") or 0)
            for c in it.get("ItemChargeList") or []:
                amt = money(c.get("ChargeAmount"))
                if _is_tax(c.get("ChargeType")):
                    s["vat"] += amt
                else:
                    s["sales_net"] += amt
            for fe in it.get("ItemFeeList") or []:
                amt = money(fe.get("FeeAmount"))
                s["fees"] += amt
                fee_types[fe.get("FeeType")] += amt
            for p in it.get("PromotionList") or []:
                amt = money(p.get("PromotionAmount"))
                s["sales_net"] += amt
                promos += amt

    for e in ev.get("RefundEventList", []):
        for it in e.get("ShipmentItemAdjustmentList") or []:
            s = sku[it.get("SellerSKU") or "?"]
            s["sku"] = it.get("SellerSKU") or "?"
            s["refund_units"] += abs(int(it.get("QuantityShipped") or 0))
            for c in it.get("ItemChargeAdjustmentList") or []:
                amt = money(c.get("ChargeAmount"))
                if _is_tax(c.get("ChargeType")):
                    s["refund_vat"] += amt
                else:
                    s["refunds_net"] += amt
            for fe in it.get("ItemFeeAdjustmentList") or []:
                amt = money(fe.get("FeeAmount"))
                s["refund_fees"] += amt
                fee_types[fe.get("FeeType")] += amt

    service = 0.0
    for e in ev.get("ServiceFeeEventList", []):
        for fe in e.get("FeeList") or []:
            amt = money(fe.get("FeeAmount"))
            service += amt
            fee_types[fe.get("FeeType")] += amt

    other_keys = [k for k in ev if k not in ("ShipmentEventList", "RefundEventList", "ServiceFeeEventList")
                  and ev.get(k)]

    rows, missing = [], []
    for s in sku.values():
        cost = costs.get(s["sku"])
        net_units = max(s["units"] - s["refund_units"], 0)
        s["unit_cost"] = cost
        s["cogs"] = round(-cost * net_units, 2) if cost is not None else None
        net = s["sales_net"] + s["refunds_net"]
        all_fees = s["fees"] + s["refund_fees"]
        s["profit"] = round(net + all_fees + s["cogs"], 2) if cost is not None else None
        s["margin"] = round(100 * s["profit"] / net, 1) if (s["profit"] is not None and net > 0) else None
        s["per_unit"] = round(s["profit"] / net_units, 2) if (s["profit"] is not None and net_units) else None
        for k in ("sales_net", "vat", "fees", "refunds_net", "refund_vat", "refund_fees"):
            s[k] = round(s[k], 2)
        if cost is None:
            missing.append(s["sku"])
        rows.append(s)
    rows.sort(key=lambda r: -(r["sales_net"]))

    sales_net = sum(r["sales_net"] for r in rows)
    vat = sum(r["vat"] + r["refund_vat"] for r in rows)
    refunds = sum(r["refunds_net"] for r in rows)
    item_fees = sum(r["fees"] + r["refund_fees"] for r in rows)
    cogs = sum(r["cogs"] for r in rows if r["cogs"] is not None)
    profit = sales_net + refunds + item_fees + service + cogs
    fees_out = [{"type": k, "label": FEE_LABELS.get(k, k), "amount": round(v, 2)}
                for k, v in sorted(fee_types.items(), key=lambda kv: kv[1])]
    return {"days": days, "rows": rows, "fee_types": fees_out, "missing_costs": missing,
            "other_event_types": other_keys,
            "totals": {"gross_inc_vat": round(sales_net + refunds + vat, 2), "output_vat": round(vat, 2),
                       "sales_net": round(sales_net, 2), "refunds_net": round(refunds, 2),
                       "item_fees": round(item_fees, 2), "service_fees": round(service, 2),
                       "promotions": round(promos, 2), "cogs": round(cogs, 2), "profit": round(profit, 2),
                       "margin": round(100 * profit / (sales_net + refunds), 1) if (sales_net + refunds) > 0 else None}}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                ".svg": "image/svg+xml", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        # Only answer requests addressed to this computer (blocks DNS-rebinding from web pages).
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._json({"error": "forbidden"}, 403)
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        LAST_HIT[0] = time.time()
        u = urlparse(self.path)
        q = parse_qs(u.query)
        refresh = q.get("refresh", ["0"])[0] == "1"
        try:
            days = max(1, min(int(q.get("days", ["30"])[0]), 180))
        except ValueError:
            days = 30
        try:
            if u.path == "/api/status":
                return self._json({"mode": MODE, "seller_id": CONFIG["seller_id"],
                                   "marketplace": CONFIG["marketplace_id"], "company": CONFIG["company"]})
            if u.path == "/api/sales":
                return self._json(cached(f"sales:{days}", lambda: build_sales(days), refresh))
            if u.path == "/api/stock":
                return self._json(cached("stock", lambda: build_stock(refresh), refresh))
            if u.path == "/api/finance":
                return self._json(cached(f"finance:{days}", lambda: build_finance(days), refresh))
            path = "/index.html" if u.path in ("/", "") else u.path
            full = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
            if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
                return self._json({"error": "not found"}, 404)
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", STATIC_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except spapi.SpApiError as e:
            self._json({"error": e.message, "status": e.status}, 502)
        except Exception as e:
            traceback.print_exc()
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        if not self._guard():
            return
        LAST_HIT[0] = time.time()
        u = urlparse(self.path)
        if u.path == "/api/quit":
            self._json({"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 100000)) or b"{}")
            if u.path == "/api/eligibility":
                items = body.get("items") or []
                return self._json(check_eligibility([str(x) for x in items]))
            self._json({"error": "not found"}, 404)
        except spapi.SpApiError as e:
            self._json({"error": e.message, "status": e.status}, 502)
        except Exception as e:
            traceback.print_exc()
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)

    def idle_watch():
        # Stops the app when no browser tab has been open for IDLE_MINUTES (the page pings every minute).
        while True:
            time.sleep(60)
            if time.time() - LAST_HIT[0] > IDLE_MINUTES * 60:
                print("No open dashboard for %d minutes - stopping." % IDLE_MINUTES)
                os._exit(0)
    threading.Thread(target=idle_watch, daemon=True).start()
    print(f"RJM Amazon app running in {MODE.upper()} mode at http://127.0.0.1:{PORT}")
    if MODE == "sample":
        print("Using SAMPLE data. Run setup_keys.command once Amazon approves your app to switch to live data.")
    print("Close this window (or press Ctrl+C) to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
