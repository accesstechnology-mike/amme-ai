---
name: amme
description: "Query Amme personal finance via the REST API — fetch, edit and delete bank connections, accounts, transactions, categories and tags."
---

# Amme API

Base URL: `https://api.emma-app.com` (override with the `AMME_API_BASE` environment variable). Auth: HTTP Bearer.

This file is the orientation page. For field-level reference of every endpoint and response shape, consult `references/endpoints.md`. For the first-time multi-step OAuth bootstrap, consult `references/auth.md` (only needed when refresh fails).

---

## Auth

Tokens live in `~/.config/amme/tokens.json`. Get a valid bearer with:

```sh
scripts/auth.sh           # prints a fresh bearer to stdout
scripts/auth.sh --force   # refresh unconditionally
```

The script decodes the JWT `exp` claim and refreshes via `POST /oauth/token` if the cached token is within 60s of expiry. New tokens are written back to the same file.

The live API requires the app request signature on **every** call (it rejects requests that omit these headers):

```sh
H=(-H "User-Agent: Emma/999 CFNetwork iOS" -H "Origin: https://web.emma-app.com" -H "Referer: https://web.emma-app.com/")
curl "${H[@]}" -H "Authorization: Bearer $(scripts/auth.sh)" "https://api.emma-app.com/me"
```

If `auth.sh` reports refresh failure (e.g. revoked refresh token), run the full OAuth bootstrap from `references/auth.md` to re-create the token store.

**Rate limit:** OAuth endpoint allows ~10/min. `auth.sh` refreshes at most once per session under normal use — don't loop it.

---

## Endpoints at a glance

| Domain | Endpoints | Notes |
|---|---|---|
| User | `GET /me`, `GET /user-additional-info` | PII; cache `id` from `/me` for write calls |
| Feed | `GET /feed` | dashboard starting point: net worth, this-month, latest 3 txns |
| Transactions | `GET /transactions`, `GET /transactions/{id}`, `GET /transactions-compact`, `POST/PATCH/DELETE /transactions[/{id}]` | manual accounts only for create/delete |
| Accounts | `GET /bank-connections[/{id}]`, `GET /accounts/{id}`, `POST /accounts/`, `POST /accounts/{id}/edit`, `DELETE /accounts/{id}` | manual only for writes/deletes |
| Categories | `GET /categories` | cache once per session |
| Labels | `GET /labels` | plain string tags |
| Budgets | `GET /budgets` | |
| Subscriptions | `GET /subscriptions` | recurring charges + predictions |
| Spaces | `GET /spaces` | |
| Analytics | `GET /analytics/{merchants,merchants/{id},categories,totals,committed}` | date-filtered totals |
| Balance | `GET /balance-history` | descending time series |
| Notifications | `GET /notifications` | `/feed.notifications.items` is empty — use this |

Full params, response shapes, and per-endpoint detail: `references/endpoints.md`.

---

## Must-know quirks

- **Creates/deletes are manual-only.** POST/DELETE on transactions and POST/DELETE on accounts require the underlying account to have `provider: "MANUAL"`. Refuse to delete bank-synced data, but editing is fine.
- **Confirm before destructive actions.** Always ask before DELETE on a transaction or account.
- **PATCH /transactions/** takes a *bare JSON array*, not an object. One element per transaction, `id` plus only the changed fields.
- **POST /transactions/ response twist:** the `customName` you send comes back in `counterpartName` and `realCounterpartName`, with `customName: null`. Looks wrong, is normal.
- **POST /transactions/ requirements:** include `updateAccountBalance: true` (otherwise the balance won't move) and `userId` (get from `/me`).
- **Narrative:** use `customName`, fall back to `counterpartName` if null.
- **Date:** `customDate` overrides `bookingDate` when set.
- **No server-side date filter on `/transactions`.** Use `/analytics/categories` or `/analytics/totals` for date-windowed totals, or fetch and filter client-side.
- **Categories:** PATCH wants `id` (e.g. `"groceries"`), not `displayName`. Cache the mapping from `GET /categories`.
- **Account types:** `CHECKING`, `SAVINGS`, `INVESTMENT`, `CREDITCARD` are all creatable as manual accounts. UK "current account" = `CHECKING`.
- **`isPending: true` transactions are read-only** — PATCH/DELETE will fail.
- **Pagination:** `/transactions` and `/transactions-compact` paginate via `page` + `perPage`. Compact is ~3× smaller and bundles a `categories` + `merchants` dictionary.
- **Balance history is descending** by timestamp (newest first).

---

## Recipes

Recipes assume:

```sh
B=https://api.emma-app.com
T=$(scripts/auth.sh)
# Required on every call — the live API rejects requests without the app signature:
H=(-H "User-Agent: Emma/999 CFNetwork iOS" -H "Origin: https://web.emma-app.com" -H "Referer: https://web.emma-app.com/")
```

### Dashboard snapshot (feed)

```sh
curl -s "${H[@]}" -H "Authorization: Bearer $T" "$B/feed" \
  | jq '{
      overview,
      thisMonth,
      thisWeek,
      latestTransactions: [.latestTransactions[:3][] | {name: (.customName // .counterpartName), amount, currency, date: .bookingDate, category: .category.displayName}]
    }'
```

Note: the array key is `.latestTransactions`, not `.transactions.items`.

### Find an account by name

```sh
curl -s "${H[@]}" -H "Authorization: Bearer $T" "$B/bank-connections" \
  | jq '[.bankConnections[].accounts[] | select(.name == "Chase")] | .[0]'
```

### Spending by category last month

```sh
curl -s "${H[@]}" -H "Authorization: Bearer $T" \
  "$B/analytics/categories?dateFrom=2026-04-01&dateTo=2026-04-30" \
  | jq '.categories | sort_by(.total) | map({displayName, total, transactionsCount})'
```

### Monthly spend trend (last 12 months)

```sh
curl -s "${H[@]}" -H "Authorization: Bearer $T" \
  "$B/analytics/totals?dateFrom=2025-06-01&dateTo=2026-05-31&step=month" \
  | jq '.totals[] | {from, spending, income, committed}'
```

### Net worth over the last year

```sh
curl -s "${H[@]}" -H "Authorization: Bearer $T" \
  "$B/balance-history?from=2025-05-31&to=2026-05-31&step=1day" \
  | jq '.history | reverse | map({timestamp, balance})'
```

### Add a manual transaction

```sh
USER_ID=$(curl -s "${H[@]}" -H "Authorization: Bearer $T" "$B/me" | jq '.id')
curl -s -X POST "${H[@]}" -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d "$(jq -n --argjson uid "$USER_ID" '{
    accountId: 9999999,
    amount: -50,
    bookingDate: "2026-01-20T00:00:00+00:00",
    categoryId: "groceries",
    currency: "GBP",
    customName: "Tesco topup",
    updateAccountBalance: true,
    userId: $uid
  }')" \
  "$B/transactions/"
```

### Bulk re-categorise transactions

```sh
curl -s -X PATCH "${H[@]}" -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '[{"id":"11111111111","categoryId":"groceries"},{"id":"22222222222","categoryId":"groceries"}]' \
  "$B/transactions/"
```

### Lifetime spend on one merchant

```sh
# Find merchantId via /analytics/merchants, then:
curl -s "${H[@]}" -H "Authorization: Bearer $T" "$B/analytics/merchants/123456" | jq '.spending'
```

### Build a category-name → id lookup

```sh
curl -s "${H[@]}" -H "Authorization: Bearer $T" "$B/categories" \
  | jq 'reduce .categories[] as $c ({}; .[$c.displayName] = $c.id)'
```
