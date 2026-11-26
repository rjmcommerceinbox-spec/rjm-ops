#!/bin/bash
# Checks the SP-API keys saved in Keychain and tests the Amazon login. Never prints the keys themselves.
cd "$(dirname "$0")" || exit 1
/usr/bin/python3 - <<'PY'
import json, urllib.parse, urllib.request, urllib.error
import spapi

EXPECT = {
    "client_id": ("amzn1.application-oa2-client.", "LWA client identifier"),
    "client_secret": ("amzn1.oa2-cs.v1.", "LWA client secret"),
    "refresh_token": ("Atzr|", "Refresh token"),
}
print("RJM Amazon app - key check (values are never shown)\n")
vals, ok_all = {}, True
for key, service in spapi.KEYCHAIN_SERVICES.items():
    v = spapi._keychain_get(service)
    prefix, label = EXPECT[key]
    if not v:
        print(f"  ✕ {label}: NOT SAVED"); ok_all = False; continue
    vals[key] = v
    problems = []
    if not v.startswith(prefix):
        # spot swapped values
        swapped = [EXPECT[k][1] for k in EXPECT if k != key and v.startswith(EXPECT[k][0])]
        problems.append(f"doesn't start with '{prefix}'" + (f" - looks like the {swapped[0]}" if swapped else ""))
    if any(c.isspace() for c in v):
        problems.append("contains a space or line break")
    if key == "refresh_token" and len(v) < 300:
        problems.append("looks cut short (real refresh tokens are 400+ characters)")
    status = "✓" if not problems else "✕"
    if problems: ok_all = False
    print(f"  {status} {label}: {len(v)} characters" + ("" if not problems else " - " + "; ".join(problems)))

print()
if len(vals) == 3:
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": vals["refresh_token"].strip(),
                                   "client_id": vals["client_id"].strip(), "client_secret": vals["client_secret"].strip()}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(spapi.LWA_URL, data=body, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}), timeout=30) as r:
            json.loads(r.read())["access_token"]
        print("✓ LOGIN WORKS - Amazon accepted the keys.")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except Exception:
            err = {}
        code = err.get("error", str(e.code))
        print(f"✕ LOGIN FAILED: {code} - {err.get('error_description', '')}")
        if code == "invalid_client":
            print("  → The client identifier or client secret is wrong. Copy both again from")
            print("    Developer Central → your app → LWA credentials → View, then run setup_keys.command.")
        elif code == "invalid_grant":
            print("  → The refresh token is wrong or expired. Get a new one from")
            print("    Developer Central → your app → Authorize → Authorize app, then run setup_keys.command.")
    except Exception as e:
        print(f"✕ Couldn't reach Amazon to test the login ({type(e).__name__}). Check the internet connection and try again.")
else:
    print("Some keys are missing - run setup_keys.command.")
PY
echo
read -r -p "Press Return to close."
