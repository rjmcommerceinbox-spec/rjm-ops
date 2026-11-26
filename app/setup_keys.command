#!/bin/bash
# Stores RJM's SP-API credentials in the macOS Keychain (never in a file).
# Run once after Amazon approves the app and you've created the app client + self-authorised it.
cd "$(dirname "$0")" || exit 1
echo "RJM Amazon app - store SP-API keys in your Mac's Keychain"
echo "-----------------------------------------------------------"
echo "You'll need, from Solution Provider Portal > Developer Central > your app:"
echo "  1. LWA client identifier   (View under 'LWA credentials')"
echo "  2. LWA client secret"
echo "  3. Refresh token           (Authorize > Authorize app)"
echo
echo "Each value is typed or pasted twice and is NOT shown on screen."
echo

store() {
  local service="$1" label="$2"
  echo ">>> $label"
  security add-generic-password -U -a rjm -s "$service" -l "$service" -w
  if [ $? -eq 0 ]; then echo "    saved."; else echo "    NOT saved - try again."; fi
  echo
}

store "RJM SP-API client_id" "LWA client identifier (starts amzn1.application-oa2-client.)"
store "RJM SP-API client_secret" "LWA client secret"
store "RJM SP-API refresh_token" "Refresh token (starts Atzr|)"

echo "Done. Close any running app window, then double-click start.command."
echo "The banner at the top should turn green: 'Live: connected to your Amazon UK seller account'."
echo
echo "To remove the keys later: open Keychain Access and search 'RJM SP-API'."
read -r -p "Press Return to close."
