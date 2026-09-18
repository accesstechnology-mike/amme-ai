# Amme Skill and MCP Server

> [!NOTE]
> **Fork purpose — live Emma API MCP.** This fork ([`accesstechnology-mike/amme-ai`](https://github.com/accesstechnology-mike/amme-ai), forked from [`lucianf/amme-ai`](https://github.com/lucianf/amme-ai)) spikes this project as a **live Emma personal-finance MCP** for Mike Thrussell / Access Technology, replacing the stale Google Sheets "Emma transactions" connector.
>
> Two corrections make the live connection work:
> - **Base URL fix.** Upstream defaulted to `https://api.amme-app.com`, which does **not** resolve (the API is a reverse-engineered Emma endpoint). The default API base is now `https://api.emma-app.com`, still overridable via the `AMME_API_BASE` environment variable.
> - **Read-only posture.** For this spike the MCP server exposes **read-only** tools only (accounts, feed/transactions, balances, categories, analytics). Mutating tools (create/edit/delete transactions and accounts) are gated behind `AMME_ENABLE_WRITE_TOOLS`, which defaults to OFF.
>
> This fork does not implement finance policy or spend advice, and stores no user credentials. The live-login auth probe is owned separately; the code and base URL here are set up so that probe works.

An unofficial AI-agent integration for the Amme (Emma) personal finance API. This repository provides two ways for an agent to work with the data:

- a portable agent skill containing API guidance, examples, and a detailed endpoint reference;
- a Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server exposing the API as structured tools.

Both integrations use the same shell script to read, validate, and refresh OAuth tokens.

> [!WARNING]
> This project can access sensitive financial and personal data. It also includes tools that can change or delete data. Review the code, keep your token file private, and use it only with agents and MCP clients you trust.

This is a community project and is not affiliated with or endorsed by Amme. It uses APIs that may change without notice.

## What's included

```text
.
├── mcp/
│   ├── amme_client.py          # Authenticated HTTP client shared by MCP tools
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

`skill/SKILL.md` teaches an agent how to query and manage Amme data directly with `curl`. It covers accounts, bank connections, transactions, categories, labels, budgets, subscriptions, analytics, notifications, balance history, and user data. It also records important API behaviour such as manual-account restrictions, pending-transaction rules, category IDs, pagination, and transaction naming and date precedence.

The reference files separate the long-form endpoint documentation and the one-time OAuth bootstrap from the everyday instructions, keeping the main skill concise.

### MCP server

`mcp/server.py` exposes tools over stdio. In the default **read-only** posture it registers **27 read-only tools**:

- dashboard, profile, notification, and feature-flag queries;
- transaction listing (`list_transactions`, `get_transaction`, `list_transactions_compact`);
- bank connection and account reads (`list_bank_connections`, `get_bank_connection`, `get_account`);
- categories, labels, budgets, subscriptions, and spaces;
- category, merchant, committed-spend, totals, and balance-history analytics;
- credit-score, data-breach, and automation-rule queries.

**Write tools are disabled by default for this spike.** The six mutating tools — `create_transaction`, `update_transactions`, `delete_transaction`, `create_account`, `edit_account`, `delete_account` — are only registered when `AMME_ENABLE_WRITE_TOOLS` is set to a truthy value (`1`, `true`, `yes`, `on`). With the flag off they are never advertised to the MCP client, so no transfers, payments, or other money-moving operations are exposed.

Read-only and destructive tools carry MCP annotations. When write tools are enabled, destructive account and transaction tools additionally require `confirm=True`, and the server documents Amme's restriction that creation and deletion operations apply only to manual accounts.

### Shared authentication

`scripts/auth.sh` reads credentials from `~/.config/amme/tokens.json` by default. It decodes the access token's JWT expiry and, when fewer than 60 seconds remain, exchanges the refresh token for a new token pair and atomically updates the file. The valid bearer token is printed to stdout so it can be consumed by either `curl` or the MCP server.

The token file is deliberately kept outside this repository. Never commit it.

## Requirements

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/) for the locked MCP environment
- `bash`, `curl`, `jq`, and `base64` for authentication
- an Amme account and OAuth tokens

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
| `AMME_ENABLE_WRITE_TOOLS` | Set truthy (`1`/`true`/`yes`/`on`) to register the mutating MCP tools. Leave unset/OFF to keep the server read-only | _unset (read-only)_ |

Authentication tokens are read from the token file (or the SMS-OTP/PIN bootstrap in [`skill/references/auth.md`](skill/references/auth.md)) by `scripts/auth.sh`; they are **not** configured via environment variables and must never be committed. See [Authentication setup](#authentication-setup) below.

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
    "amme": {
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

By default the server starts in read-only mode — only the 27 read tools are registered. To point it at a non-default host, add `"AMME_API_BASE": "https://api.emma-app.com"` to the `env` block (this is already the default). To enable the mutating tools, add `"AMME_ENABLE_WRITE_TOOLS": "true"` to the `env` block; leave it unset to keep the read-only spike posture.

## Install the agent skill

Copy or symlink `skill/` into your agent's skills directory using the name `amme`. Keep this repository's `scripts/auth.sh` available, then either run commands from the repository root or update the installed skill's examples to use the script's absolute path.

The exact skill directory and discovery mechanism depend on the agent host. Once installed, ask the agent to use the `amme` skill when working with your finances.

## Direct API use

The shared auth helper also works without MCP:

```sh
curl -sS \
  -H "Authorization: Bearer $(./scripts/auth.sh)" \
  "https://api.emma-app.com/feed"
```

See [`skill/SKILL.md`](skill/SKILL.md) for common recipes and [`skill/references/endpoints.md`](skill/references/endpoints.md) for the complete API reference.

## Security and API safety

- Treat `tokens.json` like a password. Do not paste it into prompts, logs, issues, or commits.
- Run only trusted MCP clients and agents; MCP tool results can contain financial data and personally identifiable information.
- Confirm account and transaction IDs before writes.
- Amme permits creates and deletes only for manual accounts (`provider: "MANUAL"`).
- Pending transactions are read-only.
- OAuth endpoints are rate-limited; do not repeatedly force refreshes.
- Account deletion also deletes its transactions and cannot be undone through this project.

## Development

Run a lightweight syntax check with:

```sh
uv --directory mcp run python -m compileall server.py amme_client.py
bash -n scripts/auth.sh
```

The API reference records when endpoints were last verified. If Amme changes a response or route, update both the MCP tool and the relevant skill documentation so the two interfaces remain consistent.

## License

Licensed under the [Apache License 2.0](LICENSE).
