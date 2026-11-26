# Guardrails – RJM Commerce automation

## Money and actions
- Approval required (clear yes from Rob, per action number): spending, purchase orders, supplier emails, live listing changes, price changes, accounts changes, Amazon shipments.
- Prices never set below the minimum price. Don't follow Amazon's price down.
- Automations READ data by default. Any write to Amazon is a separate, approved step.
- Emails are drafted, never sent without approval.

## Keys and security (see RJM SP-API Security Policy)
- SP-API credentials stay in the Mac Keychain only. Never committed, emailed, pasted or shared.
- Amazon data pulls run on Rob's Mac, not in GitHub's cloud, unless the security policy is updated first.
- Repo stays private; GitHub two-factor login on; Claude app limited to this repo only.
- No customer personal data in the repo (`.gitignore` blocks common files).
- Suspected key exposure: rotate the client secret in the Solution Provider Portal and re-run setup_keys.command.

## Data safety
- Never delete. Archive to `archive/` with a dated note.
- No force-pushes or history rewrites.
- Backups to Google Drive "RJM Ops Backup".

## Avoiding repeat mistakes
- Check DECISIONS.md, project memory and past chats before proposing anything.
- Flag any conflict with an earlier decision.
- Log every decision with date and Rob's approval.

## Cost control
- Pull each data source once a week (Monday run). Short answers between runs.
- Paid tools (Supermetrics, Reply.io) only when they clearly pay for themselves.
