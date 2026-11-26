"""Minimal Amazon Selling Partner API client for RJM Commerce (UK marketplace).

Standard library only. Credentials are read from the macOS Keychain (set up with
setup_keys.command) or, on other systems, from environment variables. They are
never written to disk by this app.
"""
import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"
LWA_URL = "https://api.amazon.com/auth/o2/token"
UK_MARKETPLACE = "A1F83G8C2AR07P"
USER_AGENT = "RJM-Internal-App/1.0 (Language=Python; Platform=macOS)"

KEYCHAIN_ACCOUNT = "rjm"
KEYCHAIN_SERVICES = {
    "client_id": "RJM SP-API client_id",
    "client_secret": "RJM SP-API client_secret",
    "refresh_token": "RJM SP-API refresh_token",
}
ENV_VARS = {
    "client_id": "SPAPI_CLIENT_ID",
    "client_secret": "SPAPI_CLIENT_SECRET",
    "refresh_token": "SPAPI_REFRESH_TOKEN",
}


class SpApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"SP-API {status}: {message}")
        self.status = status
        self.message = message


def _keychain_get(service):
    if platform.system() != "Darwin":
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w"],
            capture_output=True, text=True, timeout=10,
        )
        val = out.stdout.strip()
        return val or None
    except Exception:
        return None


def load_credentials():
    """Return dict of credentials, or None if any are missing."""
    creds = {}
    for key, service in KEYCHAIN_SERVICES.items():
        creds[key] = os.environ.get(ENV_VARS[key]) or _keychain_get(service)
    if all(creds.values()):
        return creds
    return None


class SpApiClient:
    def __init__(self, creds, seller_id, marketplace_id=UK_MARKETPLACE):
        self.creds = creds
        self.seller_id = seller_id
        self.marketplace_id = marketplace_id
        self._token = None
        self._token_expiry = 0

    # ---- auth -------------------------------------------------------------
    def _access_token(self):
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": self.creds["refresh_token"],
            "client_id": self.creds["client_id"],
            "client_secret": self.creds["client_secret"],
        }).encode()
        req = urllib.request.Request(LWA_URL, data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise SpApiError(e.code, "Login with Amazon token refresh failed - check the keys in Keychain. "
                             + e.read().decode(errors="replace")[:300])
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 3600))
        return self._token

    # ---- generic request with retry on throttling --------------------------
    def get(self, path, params=None, retries=5):
        url = ENDPOINT + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        delay = 2.0
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, headers={
                "x-amz-access-token": self._access_token(),
                "user-agent": USER_AGENT,
                "accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                if e.code in (429, 500, 503) and attempt < retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                try:
                    errs = json.loads(text).get("errors") or []
                    msg = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in errs) or text[:300]
                except Exception:
                    msg = text[:300]
                raise SpApiError(e.code, msg)
        raise SpApiError(429, "Still throttled after retries")

    # ---- Catalog ----------------------------------------------------------
    def catalog_by_ean(self, ean):
        d = self.get("/catalog/2022-04-01/items", {
            "identifiers": ean, "identifiersType": "EAN",
            "marketplaceIds": self.marketplace_id, "includedData": "summaries",
        })
        items = d.get("items") or []
        return items[0] if items else None

    def catalog_item(self, asin):
        try:
            return self.get(f"/catalog/2022-04-01/items/{asin}", {
                "marketplaceIds": self.marketplace_id, "includedData": "summaries,salesRanks",
            })
        except SpApiError as e:
            if e.status == 404:
                return None
            raise

    # ---- Listings restrictions (eligibility) ---------------------------------
    def restrictions(self, asin, condition="new_new"):
        return self.get("/listings/2021-08-01/restrictions", {
            "asin": asin, "sellerId": self.seller_id,
            "marketplaceIds": self.marketplace_id, "conditionType": condition,
        })

    # ---- FBA inventory ------------------------------------------------------
    def inventory_summaries(self):
        out, token = [], None
        while True:
            params = {
                "details": "true", "granularityType": "Marketplace",
                "granularityId": self.marketplace_id, "marketplaceIds": self.marketplace_id,
            }
            if token:
                params["nextToken"] = token
            d = self.get("/fba/inventory/v1/summaries", params)
            out += (d.get("payload") or {}).get("inventorySummaries") or []
            token = (d.get("pagination") or {}).get("nextToken")
            if not token:
                return out
            time.sleep(0.6)

    # ---- FBA inbound (v0) ----------------------------------------------------
    def inbound_shipments(self):
        statuses = "WORKING,READY_TO_SHIP,SHIPPED,IN_TRANSIT,DELIVERED,CHECKED_IN,RECEIVING"
        out, token = [], None
        while True:
            if token:
                params = {"MarketplaceId": self.marketplace_id, "QueryType": "NEXT_TOKEN", "NextToken": token}
            else:
                params = {"MarketplaceId": self.marketplace_id, "QueryType": "SHIPMENT",
                          "ShipmentStatusList": statuses}
            d = self.get("/fba/inbound/v0/shipments", params)
            p = d.get("payload") or {}
            out += p.get("ShipmentData") or []
            token = p.get("NextToken")
            if not token:
                return out
            time.sleep(0.6)

    def inbound_items(self, shipment_id):
        d = self.get(f"/fba/inbound/v0/shipments/{shipment_id}/items",
                     {"MarketplaceId": self.marketplace_id})
        return (d.get("payload") or {}).get("ItemData") or []

    # ---- Orders (no buyer PII requested) -------------------------------------
    def orders(self, created_after_iso):
        out, token = [], None
        while True:
            params = {"MarketplaceIds": self.marketplace_id, "CreatedAfter": created_after_iso,
                      "MaxResultsPerPage": 100}
            if token:
                params = {"MarketplaceIds": self.marketplace_id, "NextToken": token}
            d = self.get("/orders/v0/orders", params)
            p = d.get("payload") or {}
            out += p.get("Orders") or []
            token = p.get("NextToken")
            if not token:
                return out
            time.sleep(1.1)

    def order_items(self, order_id):
        d = self.get(f"/orders/v0/orders/{order_id}/orderItems")
        return (d.get("payload") or {}).get("OrderItems") or []

    # ---- Finances --------------------------------------------------------------
    def financial_events(self, posted_after_iso):
        merged, token = {}, None
        while True:
            params = {"PostedAfter": posted_after_iso, "MaxResultsPerPage": 100}
            if token:
                params = {"NextToken": token}
            d = self.get("/finances/v0/financialEvents", params)
            p = d.get("payload") or {}
            for k, v in (p.get("FinancialEvents") or {}).items():
                if isinstance(v, list):
                    merged.setdefault(k, []).extend(v)
            token = p.get("NextToken")
            if not token:
                return merged
            time.sleep(2.1)
