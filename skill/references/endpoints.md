# Amme Personal Finance API — Endpoint Reference

Base URL: `https://api.emma-app.com` (override with the `AMME_API_BASE` environment variable)
Auth: `Authorization: Bearer <token>`

Verified live: 2026-05-29

---

## Auth

Use `scripts/auth.sh` to get a bearer token — it reads `~/.config/amme/tokens.json`, refreshes via `POST /oauth/token` (grant_type=refresh_token) when the JWT is near expiry, and writes new tokens back.

The live API requires the app request signature on every call — `User-Agent: Emma/999 CFNetwork iOS`, `Origin: https://web.emma-app.com`, `Referer: https://web.emma-app.com/`:

```sh
H=(-H "User-Agent: Emma/999 CFNetwork iOS" -H "Origin: https://web.emma-app.com" -H "Referer: https://web.emma-app.com/")
curl "${H[@]}" -H "Authorization: Bearer $(scripts/auth.sh)" "$BASE/feed"
```

OAuth endpoint is rate-limited (~10/min). Only consult `references/auth.md` for the full multi-step OAuth bootstrap when refresh fails (e.g. revoked refresh token).

---

## Feed

`GET /feed`

Rich dashboard summary. Top-level keys:
- `overview` — net worth snapshot: `available`, `saved`, `creditCardDebt`, `overdraftDebt`, `loanDebt`, `totalDebt`, `investments`, `pensions`, `netWorth`, `totalAssets`, `vehicles`, `realEstate`, `others`
- `thisMonth` — spending summary: `spending`, `income`, `committed`, `committedIncome`, `budget`, `from`, `to`, `usePayday`, `isCalendarMonth`
- `latestTransactions` — last 3 transactions (plain array, **not** `.transactions.items`)
- `thisWeek` — `{ from, to, spending: { amount, currency } }`
- `subscriptions` — active subscriptions (subset)
- `paydayCountdown`, `categoriesGraph`, `notifications`, `numberOfUnreadNotifications`
- `weeklyReportCoverInfo`, `monthlyReportCoverInfo`, `yearlyReportCoverInfo`

Related: `GET /pop-ups` returns pending modal pop-ups (typically empty). `GET /recommendations` returns product recommendations (typically empty).

---

## Transactions

| Method | Path | Notes |
|---|---|---|
| GET | `/transactions` | Full details. Params: `withoutInternal`, `page`, `perPage`, `accountIds[]` (repeatable). No server-side date filter |
| GET | `/transactions/{id}` | Single transaction |
| GET | `/transactions-compact` | Compact list (~3× smaller) + `categories` dict + `merchants` dict in one call. No `accountIds[]` filter. Prefer this for full-history fetches |
| POST | `/transactions/` | Manual accounts only. Required: `accountId`, `categoryId`, `customName`, `bookingDate`, `amount`, `userId` (get from `/me`). Always include `updateAccountBalance: true` (otherwise the balance won't move) |
| PATCH | `/transactions/` | Bare array `[{id, ...fields}]`. Patchable: `customName`, `categoryId`, `labels`, `notes`, `amount`, `bookingDate`, `customDate`. Not allowed if `isPending: true`. Use category `id`, not `displayName` |
| DELETE | `/transactions/{id}` | Manual accounts only. Confirm before deleting |

Transaction fields (full): `id`, `userId`, `accountId`, `provider`, `bookingDate`, `customDate`, `amount`, `currency`, `nativeAmount` (foreign-currency transactions), `category`, `type`, `description`, `counterpartName`, `realCounterpartName`, `merchantId`, `merchant`, `subscriptionId`, `subscription`, `labels`, `isPending`, `customName`, `notes`, `splitFromId`, `relatedTransactionId`, `isRecurring`, `wasImportedFromFile`, `accountType`

Transaction `type` values (guessed by Emma engine, informative only): `ATM`, `BILL_PAYMENT`, `BROADBAND`, `CAR_INSURANCE`, `CASH`, `CASHBACK`, `CHEQUE`, `CORRECTION`, `CREDIT`, `DEBIT`, `DIRECT_DEBIT`, `FEE_CHARGE`, `GAS_AND_ELECTRICITY`, `INSURANCE`, `INTEREST`, `LOAN`, `MOBILE`, `MORTGAGE`, `OTHER`, `PURCHASE`, `STANDING_ORDER`, `TRANSFER`, `UNKNOWN`, `WATER`

**Quirks:**
- **Narrative**: use `customName` if set, otherwise `counterpartName`. `realCounterpartName` is the raw bank narrative.
- **Date**: `customDate` takes precedence over `bookingDate` when set.
- **No server-side date filter** on `/transactions` — use `/analytics/categories` or `/analytics/totals` for date-windowed totals, or fetch and filter client-side.
- **POST response twist**: the `customName` you send comes back in `counterpartName` and `realCounterpartName`, with `customName: null`. Looks wrong but is normal.
- **PATCH idempotency**: safe to retry — same payload produces the same result.
- **Sort order**: all list endpoints return transactions in reverse-chronological order.
- **`isPending: true`** → transaction is read-only. PATCH/DELETE will fail.

### Annotated transaction (GET /transactions/{id})

```jsonc
{
  "id": 11111111111,
  "userId": 9999,
  "accountId": 2222222,
  "provider": "MANUAL",                                    // MANUAL or OB_<bank>
  "bookingDate": "2026-01-29 00:00:00",                    // booked-on date; ISO without TZ
  "customDate": null,                                      // user override; takes precedence when set
  "amount": -9.11,                                         // negative = outflow, in account currency
  "currency": "GBP",
  "nativeAmount": { "amount": -21387, "currency": "MWK" }, // only on foreign-currency txns
  "category": { "id": "bills", "displayName": "Bills", "color": "...", "emoji": "🧾" },
  "type": "UNKNOWN",                                       // engine-guessed; can be wrong
  "counterpartName": "Spotifymw",                          // shown when customName is null
  "realCounterpartName": "Spotifymw",                      // raw bank narrative
  "customName": "Spotify",                                 // user-edited narrative
  "merchantId": null,                                      // null = unknown merchant
  "merchant": null,
  "labels": [],
  "isPending": false,                                      // true → read-only
  "wasImportedFromFile": true,
  "accountType": "CHECKING",
  "relatedTransactionId": null,                            // set on the matched leg of an internal transfer
  "notes": null
}
```

---

## Accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/bank-connections` | All banks + nested accounts |
| GET | `/bank-connections/{bankConnectionId}` | Single bank connection with live sync/consent status |
| GET | `/accounts/{accountId}` | Single account |
| POST | `/accounts/` | Create a manual account. See "Create manual account" below |
| POST | `/accounts/{accountId}/edit` | Update account fields. Body = changed fields only |
| DELETE | `/accounts/{accountId}` | Manual accounts only. Confirm before deleting |

Account types: `CHECKING`, `SAVINGS`, `INVESTMENT`, `CREDITCARD` — all four creatable as manual accounts.
**UK terminology**: a "current account" is `CHECKING`.
Manual accounts: `provider: "MANUAL"` — only these accept transaction POST/PATCH/DELETE and account edit/delete.

### Create manual account

POST `/accounts/` body:
- `type` (required) — one of `CHECKING`, `SAVINGS`, `INVESTMENT`, `CREDITCARD`
- `name` (required) — display name
- `balance` (optional, default `0`)
- `currency` (optional, default `GBP`)
- icon — one of:
  - `emoji`: any emoji string (e.g. `"🏦"`)
  - `iconProvider: "TWITTER"` + `iconProviderHandle`: a Twitter handle (e.g. `"@principality"`)

```json
{
  "name": "Principality RegSaver",
  "type": "SAVINGS",
  "balance": 1000,
  "currency": "GBP",
  "iconProvider": "TWITTER",
  "iconProviderHandle": "@principality"
}
```

Response: full account object.

### Account fields (`GET /accounts/{id}`)

`id`, `userId`, `spaceId`, `bankConnectionId`, `bankId`, `provider`, `providerId`, `name`, `availableBalance`, `postedBalance`, `currency`, `type`, `isBusiness`, `isHidden`, `iban`, `swiftBic`, `accountNumber`, `sortCode`, `hasBalanceHistory`, `transactionsCount`, `isClosed`, `isRemoved`, `iconUrl`, `customIconUrl`, `isManual`, `createdAt`, `lastSyncAt`. Credit-card accounts also expose `creditLimit`, `creditCardBalance`; overdraft-capable accounts expose `overdraftLimit`, `isOverdrawn`.

**`GET /bank-connections/{bankConnectionId}` response:** a single connection object (same shape as one element of the `/bank-connections` list, plus connection-status fields the list omits).

Top-level keys: `id`, `userId`, `bankId`, `bankInfo`, `status` (e.g. `"READY"`), `lastSuccessfulSync`, `accounts[]`, `isSyncing`, `isSyncingManual`, `needsFix`, `needsReconsent`, `needsReauth`, `statusMessage`, `isClosed`, `deactivatedOverQuota`, `migratableToOb`, `consentExpiresAt`, `proPreviewAccounts`, `ultimatePreviewAccounts`.

`bankInfo` fields: `id`, `name`, `subtitle`, `logoUrl`, `iconUrl`, `iconBase64`, `provider` (e.g. `OB_RBS`), `providerId`, `loginType` (e.g. `OAUTH2`), `loginData`, `type` (e.g. `"BANK"`), `isPrimary`, `connectionMethodText`, `parentId`, `connectorRemoved`, `pispBankId`, `hasPersonalBanking`, `hasBusinessBanking`, `supportsVrp`, `canRenewAccess`, `status: { syncStatus, consentStatus }`.

`accounts[]` entries carry the full account shape from `/accounts/{id}` (so `creditLimit`, `creditCardBalance`, `overdraftLimit`, `isOverdrawn`, `transactionsCount`, `isClosed`, `isRemoved`, `lastSyncAt`, `spaceId`, `providerId` are all present here — unlike the trimmed view in `/bank-connections`).

Use this endpoint when you need live sync/consent state for one bank (`status`, `needsReauth`, `consentExpiresAt`, per-account `lastSyncAt`) rather than walking the full list.

---

## Categories

| Method | Path | Notes |
|---|---|---|
| GET | `/categories` | Full list with emoji, color, counts, `hideFromStats`, `canSetBudget` |

Fetch once per session and cache. Build a `displayName → id` lookup. Use `id` (e.g. `"groceries"`), not `displayName`, on PATCH requests — the API 400s on names.

Category fields: `id`, `displayName`, `color`, `emoji`, `transactionsCount`, `parentCategoryId`, `hideFromStats`, `canSetBudget`, `subCategoryIds`, `priority`. The special `internal` category (displayName `"Excluded"`) is used for account-to-account transfers and has `hideFromStats: true`.

---

## Labels

| Method | Path | Notes |
|---|---|---|
| GET | `/labels` | All labels with `nOfTransactions` and `lastUsed` |

Labels are plain strings on transactions (e.g. `"cashback"`, `"reward"`).

---

## Budgets

| Method | Path | Notes |
|---|---|---|
| GET | `/budgets` | Budgets with `limit`, `currentValue`, `previousAverage`, `emoji`, `color`, `shouldRollover` |

Budget fields: `key`, `displayName`, `emoji`, `type`, `limit`, `baseLimit`, `totalLimit`, `rollingAccumulatedLimit`, `shouldRollover`, `currentValue`, `previousAverage`, `previousPeriodAverage`, `currency`

---

## Subscriptions

| Method | Path | Notes |
|---|---|---|
| GET | `/subscriptions` | Subscriptions with merchant info, price, frequency, predictions |

Subscription fields: `id`, `merchantId`, `merchantInfo`, `price`, `currency`, `paymentFrequency`, `isActive`, `firstChargeDate`, `lastChargeDate`, `totalPaid`, `priceChange`, `predictions`, `customName`, `minMonthDay`, `maxMonthDay`

---

## Spaces

| Method | Path | Notes |
|---|---|---|
| GET | `/spaces` | Returns space(s) with `id`, `name`, `type`, `isPremium`, `isUltimate`, `primaryIncome`, `currentPaydayRange`, `accountsCount` |

---

## Notifications

| Method | Path | Notes |
|---|---|---|
| GET | `/notifications` | Paged list of in-app notifications. Returns `items[]` + `paging` |

Item fields: `id`, `datetime`, `timeAgo`, `heading`, `text`, `type`, `iconUrl`, `coloredIconUrl`, `data` (type-specific payload, often includes `transactionIds`, `budgetKeys`, `spaceId`), `clickable.appLink`

Common `type` values: `PRODUCT_UPDATE`, `MESSAGE`, `SUBSCRIPTION_PAYMENT`, `PAYMENT_RECEIVED`, `NOT_SPENDING_TOO_FAST`, `SPENDING_TOO_FAST`, `OVER_BUDGET`, `OVERALL_OVER_BUDGET`, `OVERALL_SPENDING_TOO_FAST`

`/feed` exposes `numberOfUnreadNotifications` and `unreadCountBySpace` but its embedded `notifications.items` is typically empty — use `/notifications` for the actual list.

---

## Analytics

| Method | Path | Notes |
|---|---|---|
| GET | `/analytics/merchants` | Per-merchant spend aggregation. Params: `dateFrom`, `dateTo` (YYYY-MM-DD). Omit for all-time (large response) |
| GET | `/analytics/merchants/{merchantId}` | Lifetime spending stats for a single merchant |
| GET | `/analytics/categories` | Per-category aggregation. Params: `dateFrom`, `dateTo` |
| GET | `/analytics/totals` | Bucketed totals over time. Params: `dateFrom`, `dateTo`, `step`, `categoryId` (optional) |
| GET | `/analytics/committed` | Subscriptions whose predicted charges fall in the window. Params: `from`, `until` (full ISO 8601, e.g. `2022-11-01T00:00:00.000Z`) |

**`/analytics/merchants` response:** `{ merchants: [...], total, currency, transactionsCount }`

Merchant fields: `id`, `displayName`, `iconUrl`, `total` (negative = spend), `currency`, `transactionsCount`. Known merchants also include `legalName`, `website`, `category` (full object), `type`. Unknown counterparts collapse into a single row `{ id: -1, displayName: "Unknown" }`.

**`/analytics/merchants/{merchantId}` response:** `{ spending: { nTransactions, total, average, currency } }` — lifetime totals only, no date filtering.

**`/analytics/categories` response:** `{ categories: [...], total, currency, transactionsCount, spending, income }`

Category fields: `id`, `displayName`, `total`, `totalWithExcluded`, `transactionsCount`, plus standard category metadata (`color`, `emoji`, `parentCategoryId`, `hideFromStats`, `canSetBudget`, `subCategoryIds`, `priority`, `budgetLimit`, `baseLimit`, `rollingAccumulatedLimit`, `totalLimit`).

**`/analytics/totals` response:** `{ totals: [...] }`

Bucket fields (always): `from`, `to`, `value` (signed; spending negative), `spending` (always positive), `income`, `currency`, `totalBudget`, `baseLimit`, `rollingAccumulatedLimit`, `totalLimit`.

Aggregated steps (`month`, `payperiod`, `quarter`, `year`) additionally include: `isPayday`, `daysLeft`, `committed`, `committedIncome`, `numberOfExpectedIncomes`. `step=day` and `step=isoWeek` responses omit those five.

Valid `step` values: `day`, `isoWeek`, `month`, `quarter`, `year`, `payperiod`, `custom`. **`step` is effectively required** — omitting it causes `spending`, `income`, and `committed` to return `null`. `categoryId` is optional — omit to aggregate across all categories. When `categoryId` is set, `income` is typically `0` since income is its own category.

**`/analytics/committed` response:** `{ committed, subscriptions: [...] }`.

- `committed` (number) — total predicted recurring spend for the window, in the user's base currency. Matches `/feed.thisMonth.committed` and the `committed` field on `/analytics/totals` buckets that cover the same range.
- `subscriptions[]` — every subscription with at least one `predictions[].date` inside `[from, until]`. Same item shape as `/subscriptions`: `id`, `merchantId`, `merchantInfo`, `price: { amount, criteria }`, `currency`, `paymentFrequency`, `isActive`, `firstChargeDate`, `lastChargeDate`, `lastPrice`, `totalPaid`, `priceChange`, `nativePrice`, `convertedPrice`, `predictions[].date`, `customName`, `isInternal`, `minMonthDay`, `maxMonthDay`, `minAmount`, `maxAmount`, `rentCandidate`, `transactions[]`.

Param names differ from the other analytics endpoints: `from`/`until` with full ISO 8601 datetimes (e.g. `2026-05-01T00:00:00.000Z`), not the `dateFrom`/`dateTo` YYYY-MM-DD pattern.

Optional `includeInternal=true` is accepted but is a no-op — internal subscriptions are already included by default. The trailing-slash form `/analytics/committed/` works identically.

---

## Balance history

| Method | Path | Notes |
|---|---|---|
| GET | `/balance-history` | Historical balance time series. See params below |

Response: `{ from, to, currency, history: [...] }`. `history[]` is **descending** by timestamp (newest first). Each entry: `{ timestamp, balance, breakdown, currency }`.

`breakdown` keys are a subset of `{ assets, debt, investment, savings, current, creditCard, other, loans }` — the full set appears for net-worth-wide queries; filtered queries return only the relevant keys (e.g. `graphSection=EVERYDAY` → `{ assets, debt, current, creditCard }`; `accountTypes[]=INVESTMENT` → `{ assets, debt, investment }`).

**Date range (one of):**
- `from` + `to` (YYYY-MM-DD or full ISO 8601) + `step=1day` (alias `stepSize=1day`).
- `range=MAX` — all-time, bucket size auto-chosen (~weekly for one account, ~monthly for a section).
- `range=1W` / `1M` / `3M` / `6M` / `1Y` / `YTD` are rejected as the sole param: `from and to required if range is not given`.

**Filter (one of, app sends one at a time):**
- `accountIds[]={id}` (repeatable) — combined balance across listed accounts.
- `accountTypes[]={TYPE}` (repeatable) — `INVESTMENT`, `CRYPTO`, `CHECKING`, `SAVINGS`, `CREDITCARD`.
- `graphSection={EVERYDAY|SAVINGS|INVESTMENT|NET_WORTH}` — anything else 400s with the valid list.
- No filter → equivalent to `graphSection=NET_WORTH`.

**Other params:** `graphType={anything}` — accepted but ignored (the web app sometimes sends literal `graphType=undefined`).

---

## User

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | Current user profile. Param: `withWalkthrough=true` to include `walkthrough` object. Contains PII (email, phone, DOB) |
| GET | `/user-additional-info` | KYC-style profile fields (credit rating, employment, income/net-worth brackets, etc.). Wrapped in `{ userAdditionalInfo: {...} }` |
| GET | `/me/space-invites` | Pending space invitations. Param: `status=PENDING` |
| GET | `/me/space-removals` | Accounts removed from a shared space |

`/me` top-level fields: `id`, `email`, `phoneNumber`, `firstName`, `middleName`, `lastName`, `dateOfBirth`, `gender`, `title`, `userImage`, `createdAt`, `firstConnectionAt`, `currentPaydayRange`, `numberOfIncomes`, `timezone`, `locale`, `currency`, `homeCountry`, `guessedHomeCountry`, `ipCountryCode`, `nationalities`, `countryOfTaxResidence`, `referralCode`, `referralUrl`, `urlHandle`, `userUrl`, `questsSummary`, `referralsSummary`, `dayStreak`, `emmaProStatus`, `premiumSubscriptionStatus`, `pinHasBeenSet`, `pinLastChangedAt`, `isPinResettable`, `userOauths`, `walkthrough`, `lastUsedSpaceId`, `defaultSpaceId`, `vulnerableCustomerStatus`, `crispTokenId`, `crispEmailSignature`, `isTester`, `isEmailVerified`, `latestFeedbackDate`, `latestFeedbackRating`, `deletionInitiatedAt`.

`/user-additional-info` inner fields: `id`, `userId`, `creditRating`, `educationLevel`, `maritalStatus`, `dependantNumber`, `employmentIndustry`, `employmentStatus`, `employerName`, `employerAddress`, `jobTitle`, `grossAnnualSalary`, `annualIncomeMin`, `annualIncomeMax`, `liquidNetWorthMin`, `liquidNetWorthMax`, `fundingSource`, `financialGoals`, `acquisitionChannel`, `isRenting`. Most fields may be `null` if not filled in.

---

## Credit Score

| Method | Path | Notes |
|---|---|---|
| GET | `/credit-score/transunion/report` | Full TransUnion credit report (~2.3MB uncompressed) |
| GET | `/credit-score/transunion/score/history` | Score history with factors and next best action |

Feature-flagged: check `credit_score` flag via `/feature-flags/` before calling. The `creditScoreIdentityLockedAt` field on `/me` indicates when identity verification completed.

**`/credit-score/transunion/report` response:** `{ reportDate, personalInformation, accounts[] }`.

`personalInformation`: `name`, `dateOfBirth`, `currentAddress`, `previousAddresses[]`.

`accounts[]` fields: `lenderName`, `iconUrl`, `accountNumber` (masked), `balance`, `currencyCode`, `accountTypeCode` (`CC`, `PL`, etc.), `accountTypeName`, `status`, `accountStartDate`, `accountEndDate`, `limit`, `openingBalance`, `repaymentFrequency`, `defaultDate`, `defaultBalance`, `isClosed`, `lenderType`, `category`, `displayMode`, `statusSubjectiveLevel` (`Good`, `Fair`, `Poor`), `customLabel` (`{ balance, limit, startingBalance }`).

`statusHistory[]` — per-year array with `months[]`: `month`, `paymentStatus` (`"0"` = up to date), `paymentStatusDescription`, `accountStatus` (`OK`, `D` = default, etc.), `accountDescription`.

`balanceHistory[]` / `limitHistory[]` — per-year monthly arrays with `value`.

`accountHolderDetails`: `name`, `address`, `dateOfBirth`, `startDate`, `endDate`, `accountHolderId`.

---

**`/credit-score/transunion/score/history` response:** `{ history: [...] }`.

Each history entry: `date`, `value` (numeric score), `factors`, `nextBestAction`, `nextBestActionId`, `nextBestActionDisplayTitle`.

`factors` has three keys — `red` (negative), `yellow` (neutral/improving), `green` (positive) — each an array of `{ id, type, message }`.

Common factor types: `Credit utilisation`, `Electoral register`, `Payment history`, `Credit limit`, `Account age`, `Recent applications`.

---

## Data Breaches

| Method | Path | Notes |
|---|---|---|
| GET | `/data-breaches` | Paged list of data breaches affecting monitored accounts. Params: `page`, `perPage` |
| GET | `/data-breaches/monitored-accounts` | Email addresses currently being monitored for breaches |

**`/data-breaches` params:** `page` (default 1), `perPage` (default 20).

**`/data-breaches` response shape (inferred):** `{ items: [...], paging: { page, perPage, totalCount } }`. Each breach item likely includes breach name, date, affected data types, and which monitored account was affected.

**`/data-breaches/monitored-accounts` response:** list of monitored email entries with monitoring status.

---

## Automation Rules

| Method | Path | Notes |
|---|---|---|
| GET | `/automation-rules/` | Smart rules for auto-categorisation and transaction labelling |

**`/automation-rules/` response (inferred):** array of rule objects. Rules likely include match conditions (merchant, amount range, keyword) and actions (set category, add label, set custom name). Response is ~1KB suggesting a handful of rules per user.

Note the trailing slash is required — `/automation-rules` (no slash) may 404.

---

## Feature Flags

| Method | Path | Notes |
|---|---|---|
| GET | `/feature-flags/` | Evaluate one or more feature flags for the current user |

**Params:** `flags[]` — repeatable query param, one flag name per occurrence. The app requests ~100 flags in a single call.

**Example request:**
```
GET /feature-flags/?flags[]=credit_score&flags[]=csv_imports&flags[]=auto_invest_v4
```

**Response:** `{ flags: { flag_name: boolean|object, ... } }` — one key per requested flag.

**Known flag names (from app traffic):** `credit_score`, `credit_score_reports`, `credit_score_alerts`, `credit_score_history`, `csv_imports`, `auto_invest_v4`, `automated_savings_v2`, `isa_transfer`, `JISA`, `physical_assets`, `rent_reporting_two`, `data_breaches` (inferred), `spending-groups`, `automation-rules`.

Useful for checking whether a feature is enabled before attempting to use its endpoint.

---

## Other discovered endpoints (undocumented)

These were observed in live traffic but not fully reverse-engineered:

| Endpoint | Notes |
|---|---|
| `GET /me/space-invites?status=PENDING` | Pending invitations to join another user's space |
| `GET /me/space-removals` | Accounts removed from a shared space |
| `GET /spending-groups?withNetBalance=true&withUserIds=true` | Bill-splitting groups with per-member balances |
| `GET /quests` | Gamification quests (locked/unlocked/viewed state) |
| `GET /rent-reporting` | Rent reporting status; params: `withTenancyAddress`, `withReportingAgencies`, `withTrackingStatus`, `withRentTransactions`, `isActive` |
| `GET /promotions?withNativeOffers=true` | Active promotional offers |
| `GET /wealth/trading/aum-fees` | Emma Invest AUM fee schedule |
| `GET /wealth/trading/connected-account` | Emma Invest linked account status |
| `GET /nordvpn/status` | NordVPN partnership entitlement status |
| `GET /referrals/credit` | Referral credit balance |
| `GET /pop-ups` | Pending in-app pop-up messages |
| `GET /in-app` | In-app messaging / banners |
| `GET /recommendations` | Product recommendations |
| `POST /firebase-device-token/register` | Register push notification token |
| `POST /me/appsflyer` | AppsFlyer attribution ping |

---

## Not available (404)

- `GET /accounts` (use `/bank-connections` instead)
- `GET /analytics` (use specific sub-paths like `/analytics/merchants`)
- `GET /merchants`
- `GET /user` (use `/me` instead)
