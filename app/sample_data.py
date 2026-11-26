"""Sample-data stand-in for SpApiClient.

Returns data in the same shape as the real Selling Partner API so every screen
and calculation is exercised before Amazon approves the app. Product names and
ASINs are RJM's own lines; all quantities, sales and fees are made up.
"""
import datetime as dt
import random

# sku, asin, title, price inc VAT, cost ex VAT, fba fee
PRODUCTS = [
    ("LG-75LA-QF9U", "B0BP1JHT16", "Clairefontaine Bamboo Drawing Pad A2", 38.90, 14.20, 3.86),
    ("T6-QX5I-Y0IN", "B0BRYBWNLP", "Exacompta Flex Box Navy/Light Blue", 24.99, 9.10, 3.84),
    ("QC-KF00267-BLK10-FBA-01", "B004XFAKE1", "Q-Connect Black Ballpoint Pens (Pack of 10)", 4.39, 3.03, 2.13),
    ("SAMPLE-GESEAB1Z", "B07666SCHM", "Guildhall Ergogrip Ring Binder A4", 16.89, 6.10, 3.31),
    ("SAMPLE-52-10Z", "B000NLVVT0", "Guildhall Account Book 52/10Z", 51.40, 17.90, 3.60),
    ("SAMPLE-225Z", "B000J69T20", "Guildhall Minute Book 225Z", 140.60, 42.00, 4.42),
    ("SAMPLE-PUREBOX-BLK100", "B0SAMPLE01", "Exacompta PureBox Black 100mm", 15.99, 6.40, 3.22),
    ("SAMPLE-T1027Z", "B00HTUZS74", "Goldline T1027Z Ledger", 37.81, 13.10, 3.55),
]

GATED = {"B000J6CVWU", "B000J69OI4", "B000J6A5AK", "B000SHUB9U", "B000J6F1K4",
         "B000SHOS2G", "B000SHOS44", "B000J6CT90", "B0039IQQQM", "B003NQCYC0", "B0018BUSM0"}

SAMPLE_COSTS = {p[0]: p[4] for p in PRODUCTS}

_rng = random.Random(20261120)
_now = dt.datetime(2026, 11, 20, 18, 0, tzinfo=dt.timezone.utc)


def _money(v):
    return {"CurrencyCode": "GBP", "CurrencyAmount": round(v, 2)}


def _build_orders():
    orders, items = [], {}
    n = 0
    for day in range(90, -1, -1):
        date = _now - dt.timedelta(days=day)
        # sales ramp up as stock went live mid-November
        base = 0.4 if day > 10 else 2.6
        for _ in range(_rng.randint(0, int(base * 3))):
            p = _rng.choices(PRODUCTS, weights=[3, 3, 5, 2, 1, 1, 4, 1])[0]
            qty = 1 if _rng.random() < 0.85 else 2
            n += 1
            oid = f"204-{1000000 + n:07d}-{_rng.randint(1000000, 9999999)}"
            status = "Shipped" if day > 1 else _rng.choice(["Shipped", "Pending", "Unshipped"])
            if _rng.random() < 0.03:
                status = "Canceled"
            when = date.replace(hour=_rng.randint(7, 22), minute=_rng.randint(0, 59))
            orders.append({
                "AmazonOrderId": oid, "PurchaseDate": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "OrderStatus": status, "FulfillmentChannel": "AFN", "SalesChannel": "Amazon.co.uk",
                "OrderTotal": {"CurrencyCode": "GBP", "Amount": f"{p[3] * qty:.2f}"},
                "NumberOfItemsShipped": qty if status == "Shipped" else 0,
                "NumberOfItemsUnshipped": 0 if status == "Shipped" else qty,
            })
            items[oid] = [{"ASIN": p[1], "SellerSKU": p[0], "Title": p[2], "QuantityOrdered": qty,
                           "ItemPrice": {"CurrencyCode": "GBP", "Amount": f"{p[3] * qty:.2f}"}}]
    return orders, items


ORDERS, ORDER_ITEMS = _build_orders()


class SampleClient:
    seller_id = "SAMPLE"
    marketplace_id = "A1F83G8C2AR07P"

    def catalog_by_ean(self, ean):
        p = PRODUCTS[int(ean[-3:]) % len(PRODUCTS)]
        return {"asin": p[1], "summaries": [{"itemName": p[2] + " (sample match)", "brand": "Sample"}]}

    def catalog_item(self, asin):
        for p in PRODUCTS:
            if p[1] == asin:
                return {"asin": asin, "summaries": [{"itemName": p[2], "brand": p[2].split()[0]}]}
        return {"asin": asin, "summaries": [{"itemName": f"Sample product {asin}", "brand": "Sample"}]}

    def restrictions(self, asin, condition="new_new"):
        link = {"resource": f"https://sellercentral.amazon.co.uk/hz/approvalrequest/restrictions/approve?asin={asin}",
                "verb": "GET", "title": "Request approval", "type": "text/html"}
        if asin in GATED:
            return {"restrictions": [{"marketplaceId": self.marketplace_id, "conditionType": condition, "reasons": [
                {"reasonCode": "APPROVAL_REQUIRED",
                 "message": "You need approval to list in this brand/category (sample).", "links": [link]}]}]}
        if asin.endswith("X"):
            return {"restrictions": [{"marketplaceId": self.marketplace_id, "conditionType": condition, "reasons": [
                {"reasonCode": "NOT_ELIGIBLE", "message": "You cannot list this product (sample)."}]}]}
        return {"restrictions": []}

    def inventory_summaries(self):
        out = []
        stock = [1, 9, 0, 14, 4, 3, 22, 1]
        inbound = [0, 0, 20, 0, 0, 0, 30, 0]
        for p, s, inb in zip(PRODUCTS, stock, inbound):
            out.append({
                "asin": p[1], "fnSku": "X00SAMPLE" + p[1][-3:], "sellerSku": p[0], "productName": p[2],
                "totalQuantity": s + inb + (1 if s > 5 else 0),
                "inventoryDetails": {
                    "fulfillableQuantity": s, "inboundWorkingQuantity": 0,
                    "inboundShippedQuantity": inb, "inboundReceivingQuantity": 0,
                    "reservedQuantity": {"totalReservedQuantity": 1 if s > 5 else 0},
                    "unfulfillableQuantity": {"totalUnfulfillableQuantity": 0},
                },
            })
        return out

    def inbound_shipments(self):
        return [
            {"ShipmentId": "FBA15MX3P55T", "ShipmentName": "Nov shipment - Doncaster (sample)",
             "DestinationFulfillmentCenterId": "LBA4", "ShipmentStatus": "RECEIVING"},
            {"ShipmentId": "FBA15MX3N2JL", "ShipmentName": "Nov shipment - Liverpool (sample)",
             "DestinationFulfillmentCenterId": "LPL2", "ShipmentStatus": "CLOSED"},
            {"ShipmentId": "FBA15MXD11X7", "ShipmentName": "Herbin 12300T - Coventry (sample)",
             "DestinationFulfillmentCenterId": "BHX4", "ShipmentStatus": "IN_TRANSIT"},
        ]

    def inbound_items(self, shipment_id):
        if shipment_id == "FBA15MX3P55T":
            return [{"SellerSKU": p[0], "QuantityShipped": q, "QuantityReceived": r}
                    for p, q, r in zip(PRODUCTS[:7], [0, 10, 0, 20, 6, 4, 40], [0, 10, 0, 14, 4, 3, 10])]
        if shipment_id == "FBA15MX3N2JL":
            return [{"SellerSKU": "LG-75LA-QF9U", "QuantityShipped": 2, "QuantityReceived": 2}]
        return [{"SellerSKU": "SAMPLE-HERBIN-12300T", "QuantityShipped": 36, "QuantityReceived": 0}]

    def orders(self, created_after_iso):
        cutoff = created_after_iso.replace("Z", "")
        return [o for o in ORDERS if o["PurchaseDate"].replace("Z", "") >= cutoff]

    def order_items(self, order_id):
        return ORDER_ITEMS.get(order_id, [])

    def financial_events(self, posted_after_iso):
        cutoff = posted_after_iso.replace("Z", "")
        shipments, refunds = [], []
        for o in ORDERS:
            if o["OrderStatus"] != "Shipped" or o["PurchaseDate"].replace("Z", "") < cutoff:
                continue
            it = ORDER_ITEMS[o["AmazonOrderId"]][0]
            p = next(x for x in PRODUCTS if x[0] == it["SellerSKU"])
            qty = it["QuantityOrdered"]
            gross = p[3] * qty
            net = gross / 1.2
            ev_item = {
                "SellerSKU": p[0], "QuantityShipped": qty,
                "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": _money(net)},
                                   {"ChargeType": "Tax", "ChargeAmount": _money(gross - net)}],
                "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": _money(-gross * 0.153)},
                                {"FeeType": "FBAPerUnitFulfillmentFee", "FeeAmount": _money(-p[5] * qty)}],
            }
            shipments.append({"AmazonOrderId": o["AmazonOrderId"], "PostedDate": o["PurchaseDate"],
                              "ShipmentItemList": [ev_item]})
            if _rng.random() < 0.04:
                refunds.append({"AmazonOrderId": o["AmazonOrderId"], "PostedDate": o["PurchaseDate"],
                                "ShipmentItemAdjustmentList": [{
                                    "SellerSKU": p[0], "QuantityShipped": 1,
                                    "ItemChargeAdjustmentList": [
                                        {"ChargeType": "Principal", "ChargeAmount": _money(-p[3] / 1.2)},
                                        {"ChargeType": "Tax", "ChargeAmount": _money(-(p[3] - p[3] / 1.2))}],
                                    "ItemFeeAdjustmentList": [
                                        {"FeeType": "Commission", "FeeAmount": _money(p[3] * 0.153 * 0.8)}],
                                }]})
        service = [{"PostedDate": _now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "FeeList": [{"FeeType": "Subscription", "FeeAmount": _money(-25.00)}]},
                   {"PostedDate": _now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "FeeList": [{"FeeType": "FBAStorageFee", "FeeAmount": _money(-1.84)}]}]
        return {"ShipmentEventList": shipments, "RefundEventList": refunds, "ServiceFeeEventList": service}
