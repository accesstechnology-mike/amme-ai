"""HTTP client for the live Emma personal-finance API.

Talks to ``https://api.emma-app.com`` (override with ``AMME_API_BASE``) using the
same request signature the Emma app itself sends — the reverse-engineered API
rejects requests that omit the app User-Agent / Origin / Referer headers.

Bearer tokens come from ``scripts/auth.sh`` (which reads/refreshes
``~/.config/amme/tokens.json``). If a request still comes back ``401`` — e.g. the
cached token expired mid-session — the client forces one refresh and retries.

Every response is passed through :func:`strip_sensitive`, which recursively drops
raw bank identifiers (account number, sort code, IBAN, SWIFT/BIC) so they never
leave this process.
"""

import os
import re
import subprocess
from pathlib import Path

import httpx

BASE_URL = os.environ.get("AMME_API_BASE", "https://api.emma-app.com").rstrip("/")

# Emma app request signature — required by the live API.
USER_AGENT = "Emma/999 CFNetwork iOS"
ORIGIN = "https://web.emma-app.com"

_AUTH_SCRIPT = Path(os.environ.get("AMME_AUTH_SCRIPT", "../scripts/auth.sh"))

# Raw bank identifiers that must never leave this process.
_SENSITIVE_KEY_RE = re.compile(
    r"^(accountNumber|sortCode|iban|swiftBic|account_number|sort_code|bic)$",
    re.IGNORECASE,
)


def strip_sensitive(value):
    """Recursively remove sensitive bank identifiers from any JSON-like value."""
    if isinstance(value, list):
        return [strip_sensitive(v) for v in value]
    if isinstance(value, dict):
        return {
            k: strip_sensitive(v)
            for k, v in value.items()
            if not _SENSITIVE_KEY_RE.match(k)
        }
    return value


def _bearer(force: bool = False) -> str:
    cmd = [str(_AUTH_SCRIPT)]
    if force:
        cmd.append("--force")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _headers(force: bool = False) -> dict:
    return {
        "Authorization": f"Bearer {_bearer(force)}",
        "User-Agent": USER_AGENT,
        "Origin": ORIGIN,
        "Referer": f"{ORIGIN}/",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, *, params: dict | None = None, json_body=None):
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        r = c.request(method, path, headers=_headers(), params=params, json=json_body)
        if r.status_code == 401:
            # Cached token rejected — force a refresh via auth.sh and retry once.
            r = c.request(
                method, path, headers=_headers(force=True), params=params, json=json_body
            )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {"status": "ok"}
        return strip_sensitive(r.json())


def get(path: str, params: dict | None = None):
    return _request("GET", path, params=params)


def post(path: str, body):
    return _request("POST", path, json_body=body)


def patch(path: str, body):
    return _request("PATCH", path, json_body=body)


# ---------------------------------------------------------------------------
# Response reshapers — return safe, compact subsets for the money-heavy reads.
# ---------------------------------------------------------------------------


def _money(value):
    """Normalise an Emma money value ({amount, currency}) or scalar."""
    if isinstance(value, dict) and "amount" in value:
        return {"amount": value.get("amount"), "currency": value.get("currency", "GBP")}
    return value


def collect_accounts(bank_connections_payload: dict) -> list[dict]:
    """Flatten /bank-connections into a safe per-account list (no raw identifiers)."""
    connections = (
        bank_connections_payload.get("bankConnections")
        or bank_connections_payload.get("connections")
        or []
    )
    out: list[dict] = []
    for conn in connections:
        for a in conn.get("accounts", []) or []:
            out.append(
                {
                    "id": a.get("id"),
                    "name": str(a.get("name") or a.get("accountName") or "Unknown"),
                    "type": a.get("type"),
                    "provider": a.get("provider") or conn.get("provider"),
                    "currency": a.get("currency") or "GBP",
                    "availableBalance": a.get("availableBalance"),
                    "postedBalance": a.get("postedBalance"),
                    "creditCardBalance": a.get("creditCardBalance"),
                    "creditLimit": a.get("creditLimit"),
                    "overdraftLimit": a.get("overdraftLimit"),
                    "bankConnectionId": conn.get("id"),
                    "bankConnectionStatus": conn.get("status"),
                    "isHidden": bool(a.get("isHidden")),
                    "isClosed": bool(a.get("isClosed")),
                }
            )
    return out


def collect_connection_health(bank_connections_payload: dict) -> list[dict]:
    """Per-connection consent/sync health from /bank-connections."""
    connections = (
        bank_connections_payload.get("bankConnections")
        or bank_connections_payload.get("connections")
        or []
    )
    out: list[dict] = []
    for conn in connections:
        bank_info = conn.get("bankInfo") or {}
        out.append(
            {
                "id": conn.get("id"),
                "bankName": bank_info.get("name") or conn.get("name"),
                "status": conn.get("status"),
                "statusMessage": conn.get("statusMessage"),
                "isSyncing": bool(conn.get("isSyncing")),
                "needsReauth": bool(conn.get("needsReauth")),
                "needsReconsent": bool(conn.get("needsReconsent")),
                "needsFix": bool(conn.get("needsFix")),
                "isClosed": bool(conn.get("isClosed")),
                "consentExpiresAt": conn.get("consentExpiresAt"),
                "lastSuccessfulSync": conn.get("lastSuccessfulSync"),
                "accountsCount": len(conn.get("accounts", []) or []),
            }
        )
    return out


def pick_overview(feed: dict) -> dict:
    """Net-worth style totals from /feed.overview."""
    overview = feed.get("overview") or {}
    keys = (
        "available",
        "saved",
        "creditCardDebt",
        "overdraftDebt",
        "loanDebt",
        "totalDebt",
        "investments",
        "pensions",
        "netWorth",
        "totalAssets",
        "vehicles",
        "realEstate",
        "others",
    )
    return {k: _money(overview.get(k)) for k in keys if k in overview}


def sanitize_account_detail(raw: dict) -> dict:
    """Safe subset of a single /accounts/{id} response."""
    clean = strip_sensitive(raw)
    return {
        "id": clean.get("id"),
        "name": str(clean.get("name") or "Unknown"),
        "type": clean.get("type"),
        "provider": clean.get("provider"),
        "currency": clean.get("currency") or "GBP",
        "availableBalance": clean.get("availableBalance"),
        "postedBalance": clean.get("postedBalance"),
        "creditCardBalance": clean.get("creditCardBalance"),
        "creditLimit": clean.get("creditLimit"),
        "overdraftLimit": clean.get("overdraftLimit"),
        "isHidden": bool(clean.get("isHidden")),
        "isClosed": bool(clean.get("isClosed")),
        "isManual": clean.get("isManual"),
        "lastSyncAt": clean.get("lastSyncAt"),
        "transactionsCount": clean.get("transactionsCount"),
        "bankConnectionId": clean.get("bankConnectionId"),
    }


def sanitize_transactions(payload: dict, limit: int) -> list[dict]:
    """Compact, safe transaction rows from /transactions[-compact]."""
    items = (
        payload.get("transactions")
        or payload.get("items")
        or payload.get("data")
        or []
    )
    rows: list[dict] = []
    for t in items[:limit]:
        clean = strip_sensitive(t)
        category = clean.get("category")
        if isinstance(category, dict):
            category = category.get("displayName") or category.get("id")
        rows.append(
            {
                "id": clean.get("id"),
                "date": clean.get("customDate")
                or clean.get("bookingDate")
                or clean.get("date"),
                "amount": clean.get("amount"),
                "currency": clean.get("currency") or "GBP",
                "description": clean.get("customName")
                or clean.get("counterpartName")
                or clean.get("description")
                or clean.get("merchantName")
                or clean.get("name"),
                "category": category,
                "accountId": clean.get("accountId"),
                "isPending": bool(clean.get("isPending")),
                "type": clean.get("type"),
            }
        )
    return rows
