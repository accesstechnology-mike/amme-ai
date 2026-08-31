# Amme Skill and MCP Server

An unofficial AI-agent integration for the Amme personal finance API. This repository provides two ways for an agent to work with Amme data:

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

`mcp/server.py` exposes 30 tools over stdio, including:

- dashboard, profile, notification, and feature-flag queries;
- transaction listing, creation, bulk updates, and deletion;
- bank connection and account management;
- categories, labels, budgets, subscriptions, and spaces;
- category, merchant, committed-spend, totals, and balance-history analytics;
- credit-score, data-breach, and automation-rule queries.

Read-only and destructive tools carry MCP annotations. Destructive account and transaction tools additionally require `confirm=True`, and the server documents Amme's restriction that creation and deletion operations apply only to manual accounts.

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
| `AMME_TOKENS_FILE` | OAuth token-store path | `~/.config/amme/tokens.json` |
| `AMME_API_BASE` | API base URL used during refresh | `https://api.amme-app.com` |
| `AMME_AUTH_SCRIPT` | Auth script used by the Python client | `../scripts/auth.sh` |

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

## Install the agent skill

Copy or symlink `skill/` into your agent's skills directory using the name `amme`. Keep this repository's `scripts/auth.sh` available, then either run commands from the repository root or update the installed skill's examples to use the script's absolute path.

The exact skill directory and discovery mechanism depend on the agent host. Once installed, ask the agent to use the `amme` skill when working with your finances.

## Direct API use

The shared auth helper also works without MCP:

```sh
curl -sS \
  -H "Authorization: Bearer $(./scripts/auth.sh)" \
  "https://api.amme-app.com/feed"
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
