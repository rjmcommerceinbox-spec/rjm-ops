# Decision log (newest first)

| Date | Decision / fact | Approved by | Source |
|---|---|---|---|
| 2026-11-26 | costs.csv: 7 costs added from ExaClair invoice 5580278281 (31/16Z, 38/16Z, GP2Z, GP8SZ, 53310E, 55046E, 31/5Z). 5 still blank. | Rob (invoice supplied) | invoice 5580278281 |
| 2026-11-26 | costs.csv drafted from project records: 16 SKUs costed (incl. 12 Herbin SKUs added), 11 still need invoice figures (marked NEED COST). Draft only - Rob to check before use. | pending Rob | project docs |
| 2026-11-26 | RJM Amazon App confirmed LIVE (green banner, connected to Amazon UK seller account). SP-API app client set up. | Rob | Rob confirmed in chat 15:50 |
| 2026-11-26 | RJM Amazon App code added to `app/` (scanned: no keys; logs and data/ excluded). | Rob | zip uploaded 26 Nov |
| 2026-11-26 | Private GitHub repo `rjm-ops` created as the single source of truth; guardrails adopted; backups to Google Drive "RJM Ops Backup". | Rob | Chat 26 Nov |
| 2026-11-26 | Weekly Operating Instruction adopted: one Monday 08:00 run, each data source pulled once, dashboard + numbered action list, nothing done without approval. Designed to cut token usage. | Rob | Chat 26 Nov (artifact GXNL6Y3LCNdLGrLQbZHc6E) |
| 2026-11-21 | RJM Amazon App built on Rob's Mac Desktop ("RJM Amazon App" folder): Eligibility, Stock & inbound, Sales & orders, Fees & profit. Keys via setup_keys.command into Keychain. Shows sample data until live. | Rob | Chat 21 Nov |
| 2026-11-20 | SP-API developer registration APPROVED (17:54, all 6 roles requested). Next: create private app client, self-authorise; Rob handles credentials. Go-live status to be confirmed. | Amazon | IONOS email; project doc claude/sp_api_registration_2026-11-20.md |
| 2026-11-20 | SP-API security policy written: keys never seen or pasted by Claude. | Rob | project doc claude/sp_api_security_policy_2026-11-20.md |

## Open items
- Fill costs.csv with unit costs.
- App log shows macOS blocked start.command from reading the Desktop folder ("Operation not permitted"): fix via System Settings → Privacy & Security → Files and Folders / Full Disk Access for Terminal, or move the app folder to ~/Applications.
