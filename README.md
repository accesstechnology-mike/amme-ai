# Amme Skill and MCP Server

> [!NOTE]
> **Fork purpose — live Emma API MCP.** This fork ([`accesstechnology-mike/amme-ai`](https://github.com/accesstechnology-mike/amme-ai), forked from [`lucianf/amme-ai`](https://github.com/lucianf/amme-ai)) turns this project into a **live Emma personal-finance MCP** for Mike Thrussell / Access Technology, replacing the stale Google Sheets "Emma transactions" connector.
>
> What makes the live connection work:
> - **Base URL.** The API is a reverse-engineered Emma endpoint served at `https://api.emma-app.com` (upstream's `https://api.amme-app.com` does **not** resolve). This is the default, overridable via `AMME_API_BASE`.
> - **App request signature.** The live API rejects requests that omit the Emma app headers, so the client and `scripts/auth.sh` send `User-Agent: Emma/999 CFNetwork iOS`, `Origin: https://web.emma-app.com`, and `Referer: https://web.emma-app.com/` on every call.
> - **Reads plus safe writes.** The MCP exposes 17 read tools and 5 write tools. Write tools require `confirm=true` (with `confirm=false` they return a preview and send nothing), edit **Emma metadata only** (names, categories, labels, manual entries), and **never move real bank money**. There are **no delete tools**.
> - **Privacy by default.** Raw bank identifiers (`accountNumber`, `sortCode`, `iban`, `swiftBic`) are stripped from every response.
>
> This fork does not implement finance policy or spend advice, and stores no user credentials.

An unofficial AI-agent integration for the Emma personal finance API. This repository provides two ways for an agent to work with the data:

- a Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server exposing the live API as structured tools;
- a portable agent skill containing API guidance, `curl` examples, and a detailed endpoint reference.

Both integrations use the same shell script to read, validate, and refresh OAuth tokens.

> [!WARNING]
> This project can access sensitive financial and personal data, and includes tools that can add or change data. Review the code, keep your token file private, and use it only with agents and MCP clients you trust.

This is a community project and is not affiliated with or endorsed by Emma. It uses APIs that may change without notice.

## What's included

```text
.
├── mcp/
│   ├── amme_client.py          # Emma API HTTP client (app headers, refresh, field stripping)
│   ├── pyproject.toml          # Python package metadata and dependencies
│   ├── server.py               # FastMCP server and tool definitions
│   └── uv.lock                 # Reproducible Python dependency lockfile
├── scripts/
│   └── auth.sh                 # Shared OAuth token reader and refresher
└── skill/
    ├── SKILL.md                # Agent instructions, API notes, and recipes
    └── references/
        ├── auth.md             # First-time multi-step OAuth bootstrap
        └── endpoints.md        # Full endpoint and response-field reference
```

### Agent skill

`skill/SKILL.md` teaches an agent how to query and manage Emma data directly with `curl`. It covers accounts, bank connections, transactions, categories, labels, budgets, subscriptions, analytics, notifications, balance history, and user data, including the required Emma app request headers. It also records important API behaviour such as manual-account restrictions, pending-transaction rules, category IDs, pagination, and transaction naming and date precedence.

The reference files separate the long-form endpoint documentation and the one-time OAuth bootstrap from the everyday instructions, keeping the main skill concise.

### MCP server

`mcp/server.py` (a [FastMCP](https://github.com/jlowin/fastmcp) server) exposes 22 tools over stdio against the live Emma API.

**Read tools (17)** — always available, sensitive identifiers stripped:

| Tool | Source | Purpose |
|---|---|---|
| `get_balances` | `/bank-connections` | All linked accounts with balance fields (`include_hidden` optional) |
| `get_account` | `/accounts/{id}` | One account by `account_id` or `name` |
| `get_overview` | `/feed` | Net-worth totals (available, debts, investments, netWorth, totalAssets) |
| `list_recent_transactions` | `/transactions-compact` | Recent transactions (`limit` 1–100, default 25) |
| `list_account_transactions` | `/transactions` | Transactions for one or more accounts (`account_ids[]`, `page`, `per_page`, optional `without_internal`) |
| `list_subscriptions` | `/subscriptions` | Subscriptions with price, frequency, predictions |
| `list_upcoming_committed` | `/analytics/committed` | Predicted recurring charges in a window (`date_from`/`date_to`, ISO) |
| `spend_by_category` | `/analytics/categories` | Per-category totals for a window (YYYY-MM-DD) |
| `spend_by_merchant` | `/analytics/merchants` | Per-merchant aggregation (dates optional) |
| `get_spend_totals` | `/analytics/totals` | Bucketed totals (`step`, optional `category_id`) |
| `get_balance_history` | `/balance-history` | Balance time series (`graph_section`/`account_ids`/`account_types`) |
| `list_categories` | `/categories` | Category ids, names, emoji, counts |
| `list_labels` | `/labels` | Labels with counts and last-used dates |
| `list_budgets` | `/budgets` | Budget limits vs current/previous (`displayName`, `key`, `emoji`, `shouldRollover`) |
| `list_notifications` | `/notifications` | Paged in-app notifications (`page`/`per_page`; text truncated if huge) |
| `get_credit_score_history` | `/credit-score/transunion/score/history` | Slim score history (date/value/next-best-action + factor type/message). **Not** the full TransUnion report |
| `list_bank_connection_health` | `/bank-connections` | Per-connection consent/sync health (`needsReauth`, `consentExpiresAt`, …) |

**Write tools (5)** — require `confirm=true`; with `confirm=false` they return a preview and send nothing. They edit **Emma metadata only** and **do not move real bank money**. There are **no delete tools**.

| Tool | Method | Purpose |
|---|---|---|
| `update_transaction` | `PATCH /transactions/` | Edit one transaction (customName/category/labels/notes/amount/date). Refuses pending transactions |
| `update_subscription` | `PATCH /subscriptions/{id}` | Rename a subscription (`customName`) |
| `create_manual_transaction` | `POST /transactions/` | Add a transaction to a `MANUAL` account (userId + `updateAccountBalance` handled automatically) |
| `create_manual_account` | `POST /accounts/` | Create a manual account (`CHECKING`/`SAVINGS`/`INVESTMENT`/`CREDITCARD`) |
| `update_manual_account` | `POST /accounts/{id}/edit` | Edit a `MANUAL` account (`name`/`balance`/emoji or Twitter icon). Refuses non-manual accounts |

Read tools carry the MCP `readOnlyHint` annotation; the three update tools carry `idempotentHint`. Manual writes only work on accounts with `provider: "MANUAL"`. The full TransUnion credit report (`GET /credit-score/transunion/report`) is **not** exposed.

### Shared authentication

`scripts/auth.sh` reads credentials from `~/.config/amme/tokens.json` by default. It decodes the access token's JWT expiry and, when fewer than 60 seconds remain, exchanges the refresh token for a new token pair and atomically updates the file. The valid bearer token is printed to stdout so it can be consumed by either `curl` or the MCP server.

The token file is deliberately kept outside this repository. Never commit it.

## Requirements

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/) for the locked MCP environment
- `bash`, `curl`, `jq`, and `base64` for authentication
- an Emma account and OAuth tokens

## Authentication setup

Follow [`skill/references/auth.md`](skill/references/auth.md) to complete the first-time SMS OTP and PIN flow, then save the resulting credentials at:

```text
~/.config/amme/tokens.json
```

Use permissions that prevent other local users from reading the file:

```sh
chmod 600 ~/.config/amme/tokens.json
```

Test authentication from the repository root:

```sh
./scripts/auth.sh
```

Force a refresh when needed:

```sh
./scripts/auth.sh --force
```

The following environment variables override the defaults:

| Variable | Purpose | Default |
|---|---|---|
| `AMME_API_BASE` | Emma API base URL used by the client and by `auth.sh` during token refresh | `https://api.emma-app.com` |
| `AMME_TOKENS_FILE` | OAuth token-store path (holds `client_id`, `access_token`, `refresh_token`; never commit it) | `~/.config/amme/tokens.json` |
| `AMME_AUTH_SCRIPT` | Auth script used by the Python client | `../scripts/auth.sh` |
| `AMME_LOCK_FILE` | Exclusive flock path so parallel MCP calls share one OAuth refresh | `~/.config/amme/auth.lock` |
| `AMME_LOCK_WAIT_SECONDS` | Seconds to wait for the auth lock before failing | `30` |

Authentication tokens are read from the token file (or the SMS-OTP/PIN bootstrap in [`skill/references/auth.md`](skill/references/auth.md)) by `scripts/auth.sh`; they are **not** configured via environment variables and must never be committed. See [Authentication setup](#authentication-setup) below.

Write tools are always registered but are gated at call time by `confirm` — no environment flag is needed to enable them, and no tool moves real bank money or deletes anything.

## Run the MCP server

From the repository root:

```sh
uv --directory mcp sync --locked
uv --directory mcp run python server.py
```

The server uses stdio, so an MCP client normally launches it rather than a person running it interactively. A generic client configuration looks like this (replace `/absolute/path/to/amme`):

```json
{
  "mcpServers": {
    "emma": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/amme/mcp",
        "run",
        "python",
        "server.py"
      ],
      "env": {
        "AMME_AUTH_SCRIPT": "/absolute/path/to/amme/scripts/auth.sh"
      }
    }
  }
}
```

Setting `AMME_AUTH_SCRIPT` to an absolute path makes the configuration independent of the MCP client's working directory.

All 22 tools are registered on start-up. The 5 write tools take effect only when called with `confirm=true`; called with `confirm=false` (the default) they return a preview of the request and send nothing. To point the server at a non-default host, add `"AMME_API_BASE": "https://api.emma-app.com"` to the `env` block (this is already the default).

## Install the agent skill

Copy or symlink `skill/` into your agent's skills directory using the name `amme`. Keep this repository's `scripts/auth.sh` available, then either run commands from the repository root or update the installed skill's examples to use the script's absolute path.

The exact skill directory and discovery mechanism depend on the agent host. Once installed, ask the agent to use the `amme` skill when working with your finances.

## Direct API use

The shared auth helper also works without MCP. The live API requires the Emma app headers on every call:

```sh
curl -sS \
  -H "User-Agent: Emma/999 CFNetwork iOS" \
  -H "Origin: https://web.emma-app.com" \
  -H "Referer: https://web.emma-app.com/" \
  -H "Authorization: Bearer $(./scripts/auth.sh)" \
  "https://api.emma-app.com/feed"
```

See [`skill/SKILL.md`](skill/SKILL.md) for common recipes and [`skill/references/endpoints.md`](skill/references/endpoints.md) for the complete API reference.

## Security and API safety

- Treat `tokens.json` like a password. Do not paste it into prompts, logs, issues, or commits.
- Run only trusted MCP clients and agents; MCP tool results can contain financial data and personally identifiable information.
- Raw bank identifiers (`accountNumber`, `sortCode`, `iban`, `swiftBic`) are stripped from every response by the client.
- No tool moves real bank money, and there are no delete tools. Write tools change Emma metadata (names, categories, labels) or add manual entries only.
- Write tools require `confirm=true`; with `confirm=false` they return a preview and send nothing. Confirm account and transaction IDs before setting `confirm=true`.
- Manual transactions can only be added to manual accounts (`provider: "MANUAL"`); pending transactions are read-only.
- OAuth endpoints are rate-limited; do not repeatedly force refreshes.

## Development

Run a lightweight syntax check with:

```sh
uv --directory mcp run python -m compileall server.py amme_client.py
bash -n scripts/auth.sh
```

The API reference records when endpoints were last verified. If Amme changes a response or route, update both the MCP tool and the relevant skill documentation so the two interfaces remain consistent.

## License

Licensed under the [Apache License 2.0](LICENSE).
