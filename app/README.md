# RJM Amazon App

RJM Commerce Limited's private dashboard for Amazon UK. It runs only on this Mac,
and only this Mac can open it (the address is 127.0.0.1).

## Start it
1. Double-click **start.command**. A Terminal window opens and your browser goes to http://127.0.0.1:8765
2. To stop it, close the Terminal window.

The first time, macOS may say it "cannot be opened because it is from an unidentified developer".
Right-click (or Control-click) **start.command**, choose **Open**, then click **Open** again.
You only need to do this once.

If macOS asks to install "command line developer tools", click **Install**, wait for it to finish,
then double-click start.command again. This gives you Python, which the app needs.

## Screens
- **Eligibility**: paste ASINs or barcodes to see whether RJM can sell them. For anything that needs approval, it links to Amazon's approval page.
- **Stock & inbound**: FBA stock, inbound shipments, days of cover and reorder alerts.
- **Sales & orders**: daily sales chart, sales by SKU and recent orders. No customer details are fetched.
- **Fees & profit**: settled sales, output VAT, Amazon fees by type, cost of goods, and profit and margin per SKU.
  Every table has **Export CSV** for the accountant.

## Sample data until Amazon approves you
Until the Amazon keys are added, the yellow banner says **Sample data**. All the numbers are made up.

## Go live (after Amazon approves the developer registration)
1. Solution Provider Portal > Developer Central > **Add new app client**. Choose API type **SP API**,
   then tick the same roles you were approved for.
2. On the app: **Authorize > Authorize app** gives you a **refresh token**. **LWA credentials > View** gives you the
   **client identifier** and **client secret**.
3. Double-click **setup_keys.command** and paste the three values. They are saved in the Mac's Keychain,
   not in a file, and are never shown on screen.
4. Restart start.command. The banner turns green: **Live**.

The keys stay only in Keychain (search "RJM SP-API" in Keychain Access). Never email them or paste them
into a document. If you think they've been seen by someone else, follow the incident steps in the
RJM SP-API Security Policy: rotate the client secret in the portal and run setup_keys.command again.

## Cost prices
Profit uses **costs.csv**. Fill in `unit_cost_ex_vat` for each SKU from the master inventory workbook,
then press Refresh on Fees & profit. If any SKUs have no cost, the screen lists them in a red box.

## Files
- `server.py`: the local web server, plus the sales, stock and profit calculations
- `spapi.py`: the Amazon Selling Partner API client (UK marketplace A1F83G8C2AR07P, EU endpoint)
- `sample_data.py`: the test data used before you go live
- `static/index.html`: the screens
- `config.json`: RJM's seller ID and marketplace (nothing secret)
- `data/`: a cache of order lines (SKU, quantity and price only) so Amazon doesn't have to be asked for them again
