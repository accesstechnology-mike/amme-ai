"""Live Emma API MCP server.

Exposes the reverse-engineered Emma personal-finance API (https://api.emma-app.com)
as MCP tools over stdio. Reads are always available; write tools edit Emma
*metadata only* (custom names, categories, labels, manual entries) and require
``confirm=true`` — with ``confirm=false`` they return a preview and send nothing.

No tool moves real bank money, and no DELETE tools are exposed. Raw bank
identifiers (account number, sort code, IBAN, SWIFT/BIC) are stripped from every
response by the client.
"""

from datetime import datetime, timezone

import amme_client as api
from fastmcp import FastMCP

# Money-safety statement surfaced on every write tool.
_NO_BANK_MOVEMENT = (
    "This tool edits Emma metadata only (names/categories/labels/manual entries). "
    "It does NOT move, send, or transfer real bank money."
)

mcp = FastMCP(
    name="emma",
    instructions=(
        "Live Emma personal finance assistant over the Emma API (api.emma-app.com). "
        "Read tools are always available. Write tools edit Emma metadata only — they "
        "never move real bank money and there are no delete tools. Every write tool "
        "requires confirm=true; with confirm=false it returns a preview and sends nothing. "
        "For date-windowed spending, prefer spend_by_category / get_spend_totals over "
        "listing every transaction. Use list_account_transactions to page one or more "
        "accounts. Use list_categories to resolve category display names "
        "to id strings before updating transactions. A transaction's display name is "
        "customName if set, otherwise counterpartName; results are reverse-chronological. "
        "Account type CHECKING is a UK current account — show it as 'Current account'. "
        "Manual writes (create_manual_transaction, update_manual_account) only work on "
        "accounts with provider='MANUAL'. Credit-score history is a slim score-over-time "
        "view — never fetch or dump the full TransUnion report."
    ),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wrap(endpoint: str, **payload) -> dict:
    """Attach provenance (source/endpoint/fetched_at) to a read response."""
    return {"source": "emma-api", "endpoint": endpoint, "fetched_at": _now(), **payload}


def _preview(action: str, method: str, path: str, *, body=None, note: str | None = None) -> dict:
    """Describe exactly what a write tool would do, without sending anything."""
    request: dict = {"method": method, "path": path}
    if body is not None:
        request["body"] = body
    result = {
        "preview": True,
        "confirmed": False,
        "action": action,
        "request": request,
        "safety": _NO_BANK_MOVEMENT,
        "note": "Preview only — nothing was sent. Set confirm=true to execute.",
    }
    if note:
        result["detail"] = note
    return result


# ===========================================================================
# READ TOOLS
# ===========================================================================


@mcp.tool(annotations={"readOnlyHint": True})
def get_balances(include_hidden: bool = False) -> dict:
    """All linked Emma accounts with balances (from /bank-connections).

    Returns name, type, provider, currency, and balance fields only — never account
    numbers, sort codes, or IBANs. Hidden/closed accounts are excluded unless
    include_hidden=True."""
    payload = api.get("/bank-connections")
    accounts = api.collect_accounts(payload)
    if not include_hidden:
        accounts = [a for a in accounts if not a["isHidden"] and not a["isClosed"]]
    return _wrap("/bank-connections", count=len(accounts), accounts=accounts)


@mcp.tool(annotations={"readOnlyHint": True})
def get_account(account_id: int | None = None, name: str | None = None) -> dict:
    """Fetch one Emma account by id, or by case-insensitive name match.

    Provide account_id or name. Sensitive identifiers are stripped."""
    if account_id is None and not name:
        return {"error": "Provide account_id or name."}
    matched_name = None
    resolved_id = account_id
    if resolved_id is None:
        accounts = api.collect_accounts(api.get("/bank-connections"))
        needle = name.strip().lower()
        match = next((a for a in accounts if str(a["name"]).lower() == needle), None) or next(
            (a for a in accounts if needle in str(a["name"]).lower()), None
        )
        if not match:
            return {"error": f"No account matching name: {name}"}
        resolved_id = match["id"]
        matched_name = match["name"]
    account = api.sanitize_account_detail(api.get(f"/accounts/{resolved_id}"))
    return _wrap(f"/accounts/{resolved_id}", matched_name=matched_name, account=account)


@mcp.tool(annotations={"readOnlyHint": True})
def get_overview() -> dict:
    """Net-worth overview from /feed: available, saved, debts, investments, netWorth, totalAssets."""
    feed = api.get("/feed")
    return _wrap("/feed", overview=api.pick_overview(feed))


@mcp.tool(annotations={"readOnlyHint": True})
def list_recent_transactions(limit: int = 25) -> dict:
    """Recent transactions (compact) from /transactions-compact.

    Returns date, amount, description, category, accountId, isPending — no raw account
    identifiers. limit is clamped to 1..100 (default 25), newest first."""
    limit = max(1, min(int(limit), 100))
    payload = api.get("/transactions-compact", params={"perPage": limit})
    transactions = api.sanitize_transactions(payload, limit)
    return _wrap("/transactions-compact", count=len(transactions), transactions=transactions)


@mcp.tool(annotations={"readOnlyHint": True})
def list_subscriptions() -> dict:
    """Active and inactive subscriptions with merchant info, price, frequency, and predictions."""
    return _wrap("/subscriptions", data=api.get("/subscriptions"))


@mcp.tool(annotations={"readOnlyHint": True})
def list_upcoming_committed(date_from: str, date_to: str) -> dict:
    """Predicted recurring (committed) subscription charges in a window.

    date_from/date_to: full ISO 8601 datetimes, e.g. '2026-05-01T00:00:00.000Z'
    (mapped to the API's from/until params)."""
    data = api.get("/analytics/committed", params={"from": date_from, "until": date_to})
    return _wrap("/analytics/committed", data=data)


@mcp.tool(annotations={"readOnlyHint": True})
def spend_by_category(date_from: str, date_to: str) -> dict:
    """Per-category spending totals for a date window. date_from/date_to: YYYY-MM-DD."""
    data = api.get("/analytics/categories", params={"dateFrom": date_from, "dateTo": date_to})
    return _wrap("/analytics/categories", data=data)


@mcp.tool(annotations={"readOnlyHint": True})
def spend_by_merchant(date_from: str | None = None, date_to: str | None = None) -> dict:
    """Per-merchant spending aggregation. date_from/date_to: YYYY-MM-DD.

    Omit both dates for all-time totals (can be a large response)."""
    params: dict = {}
    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to
    data = api.get("/analytics/merchants", params=params or None)
    return _wrap("/analytics/merchants", data=data)


@mcp.tool(annotations={"readOnlyHint": True})
def get_spend_totals(
    date_from: str,
    date_to: str,
    step: str = "month",
    category_id: str | None = None,
) -> dict:
    """Bucketed spending/income totals over a date range.

    date_from/date_to: YYYY-MM-DD. step: day, isoWeek, month, quarter, year, payperiod, custom
    (step is effectively required — omitting it nulls the totals). Optionally filter to one
    category_id (income is 0 when filtering by category)."""
    params: dict = {"dateFrom": date_from, "dateTo": date_to, "step": step}
    if category_id:
        params["categoryId"] = category_id
    return _wrap("/analytics/totals", data=api.get("/analytics/totals", params=params))


@mcp.tool(annotations={"readOnlyHint": True})
def get_balance_history(
    date_from: str,
    date_to: str,
    step: str = "1day",
    graph_section: str | None = None,
    account_ids: list[int] | None = None,
    account_types: list[str] | None = None,
) -> dict:
    """Balance time series (descending). date_from/date_to: YYYY-MM-DD, step: 1day.

    Use exactly one filter: graph_section (NET_WORTH default, EVERYDAY, SAVINGS, INVESTMENT),
    account_ids, or account_types (INVESTMENT, CRYPTO, CHECKING, SAVINGS, CREDITCARD)."""
    params: dict = {"from": date_from, "to": date_to, "step": step}
    if graph_section:
        params["graphSection"] = graph_section
    if account_ids:
        params["accountIds[]"] = account_ids
    if account_types:
        params["accountTypes[]"] = account_types
    return _wrap("/balance-history", data=api.get("/balance-history", params=params))


@mcp.tool(annotations={"readOnlyHint": True})
def list_categories() -> dict:
    """All spending categories with ids, display names, emoji, colours, and counts.

    Use the id field (e.g. 'groceries'), not displayName, when updating transactions."""
    return _wrap("/categories", data=api.get("/categories"))


@mcp.tool(annotations={"readOnlyHint": True})
def list_labels() -> dict:
    """All labels (tags) in use with transaction counts and last-used dates."""
    return _wrap("/labels", data=api.get("/labels"))


@mcp.tool(annotations={"readOnlyHint": True})
def list_bank_connection_health() -> dict:
    """Per-bank-connection consent/sync health from /bank-connections.

    Returns status, isSyncing, needsReauth/needsReconsent/needsFix, consentExpiresAt,
    lastSuccessfulSync, and account counts — no raw account identifiers."""
    payload = api.get("/bank-connections")
    connections = api.collect_connection_health(payload)
    return _wrap("/bank-connections", count=len(connections), connections=connections)


@mcp.tool(annotations={"readOnlyHint": True})
def get_credit_score_history() -> dict:
    """TransUnion credit *score history* only — never the full credit report.

    GET /credit-score/transunion/score/history. Each point: date, value,
    nextBestActionDisplayTitle, nextBestAction, and factors.red/yellow/green
    as {type, message} only. Does not call /credit-score/transunion/report
    (that payload is ~2.3MB of PII and is not exposed)."""
    payload = api.get("/credit-score/transunion/score/history")
    history = api.sanitize_credit_score_history(payload)
    return _wrap(
        "/credit-score/transunion/score/history",
        count=len(history),
        history=history,
    )


@mcp.tool(annotations={"readOnlyHint": True})
def list_notifications(page: int = 1, per_page: int = 20) -> dict:
    """In-app notifications from GET /notifications.

    page starts at 1; per_page is clamped to 1..100 (default 20). Returns id,
    datetime, type, heading, and text (truncated if huge). Use this — not
    /feed.notifications, which is typically empty."""
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    payload = api.get("/notifications", params={"page": page, "perPage": per_page})
    notifications = api.sanitize_notifications(payload)
    return _wrap(
        "/notifications",
        count=len(notifications),
        page=page,
        perPage=per_page,
        paging=api.pick_paging(payload),
        notifications=notifications,
    )


@mcp.tool(annotations={"readOnlyHint": True})
def list_budgets() -> dict:
    """Budgets from GET /budgets.

    Returns displayName, key, limit, currentValue, previousAverage, emoji,
    shouldRollover, and currency."""
    payload = api.get("/budgets")
    budgets = api.sanitize_budgets(payload)
    return _wrap("/budgets", count=len(budgets), budgets=budgets)


@mcp.tool(annotations={"readOnlyHint": True})
def list_account_transactions(
    account_ids: list[int],
    page: int = 1,
    per_page: int = 25,
    without_internal: bool | None = None,
) -> dict:
    """Transactions for one or more accounts from GET /transactions.

    Requires account_ids (one or more). page starts at 1; per_page is clamped
    to 1..100 (default 25). Set without_internal=True to omit internal transfers.
    Same compact sanitised fields as list_recent_transactions — no raw account
    identifiers. Newest first."""
    if not account_ids:
        return {"error": "Provide at least one account_id in account_ids."}
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 100))
    params: dict = {
        "page": page,
        "perPage": per_page,
        "accountIds[]": [int(a) for a in account_ids],
    }
    if without_internal is not None:
        params["withoutInternal"] = without_internal
    payload = api.get("/transactions", params=params)
    transactions = api.sanitize_transactions(payload)
    return _wrap(
        "/transactions",
        count=len(transactions),
        page=page,
        perPage=per_page,
        paging=api.pick_paging(payload),
        transactions=transactions,
    )


# ===========================================================================
# WRITE TOOLS — confirm=true required; confirm=false returns a preview only.
# None of these move real bank money; no delete tools are exposed.
# ===========================================================================


@mcp.tool(annotations={"idempotentHint": True})
def update_transaction(
    transaction_id: int,
    custom_name: str | None = None,
    category_id: str | None = None,
    labels: list[str] | None = None,
    notes: str | None = None,
    amount: float | None = None,
    booking_date: str | None = None,
    custom_date: str | None = None,
    confirm: bool = False,
) -> dict:
    """Edit metadata on one transaction via PATCH /transactions/ (bare array).

    Changeable: custom_name, category_id, labels, notes, amount, booking_date, custom_date.
    Pending transactions (isPending=true) are refused. category_id must be an id string
    (see list_categories). Requires confirm=true; confirm=false returns a preview.
    Does NOT move real bank money."""
    changes: dict = {}
    if custom_name is not None:
        changes["customName"] = custom_name
    if category_id is not None:
        changes["categoryId"] = category_id
    if labels is not None:
        changes["labels"] = labels
    if notes is not None:
        changes["notes"] = notes
    if amount is not None:
        changes["amount"] = amount
    if booking_date is not None:
        changes["bookingDate"] = booking_date
    if custom_date is not None:
        changes["customDate"] = custom_date
    if not changes:
        return {"error": "Provide at least one field to change."}

    current = api.get(f"/transactions/{transaction_id}")
    if isinstance(current, dict) and current.get("isPending"):
        return {"error": f"Transaction {transaction_id} is pending (isPending=true) and cannot be edited."}

    body = [{"id": transaction_id, **changes}]
    if not confirm:
        return _preview(
            "update_transaction",
            "PATCH",
            "/transactions/",
            body=body,
            note="Pending check passed. Sends a bare JSON array with one element.",
        )
    return {"status": "updated", "result": api.patch("/transactions/", body)}


@mcp.tool(annotations={"idempotentHint": True})
def update_subscription(subscription_id: int, custom_name: str, confirm: bool = False) -> dict:
    """Rename a subscription via PATCH /subscriptions/{id} with {"customName": ...}.

    Requires confirm=true; confirm=false returns a preview. Returns {subscription, status}.
    Does NOT move real bank money."""
    path = f"/subscriptions/{subscription_id}"
    body = {"customName": custom_name}
    if not confirm:
        return _preview("update_subscription", "PATCH", path, body=body)
    return {"status": "updated", "result": api.patch(path, body)}


@mcp.tool()
def create_manual_transaction(
    account_id: int,
    amount: float,
    booking_date: str,
    category_id: str,
    custom_name: str,
    currency: str = "GBP",
    notes: str | None = None,
    confirm: bool = False,
) -> dict:
    """Create a transaction on a MANUAL account via POST /transactions/.

    Only works when the account's provider is 'MANUAL'. amount is negative for spending,
    positive for income. booking_date: ISO 8601 (e.g. '2026-05-31T00:00:00+00:00').
    category_id must be an id string (see list_categories). userId is fetched from /me and
    updateAccountBalance:true is set automatically. Requires confirm=true; confirm=false
    returns a preview. Does NOT move real bank money — it only records a manual entry."""
    account = api.sanitize_account_detail(api.get(f"/accounts/{account_id}"))
    if account.get("provider") != "MANUAL":
        return {
            "error": f"Account {account_id} is not manual (provider={account.get('provider')!r}). "
            "Manual transactions can only be added to MANUAL accounts."
        }
    me = api.get("/me")
    body: dict = {
        "accountId": account_id,
        "amount": amount,
        "bookingDate": booking_date,
        "categoryId": category_id,
        "currency": currency,
        "customName": custom_name,
        "updateAccountBalance": True,
        "userId": me.get("id"),
    }
    if notes is not None:
        body["notes"] = notes
    if not confirm:
        return _preview(
            "create_manual_transaction",
            "POST",
            "/transactions/",
            body=body,
            note=f"Target account '{account.get('name')}' is MANUAL.",
        )
    return {"status": "created", "result": api.post("/transactions/", body)}


@mcp.tool()
def create_manual_account(
    name: str,
    account_type: str,
    balance: float = 0.0,
    currency: str = "GBP",
    emoji: str | None = None,
    twitter_handle: str | None = None,
    confirm: bool = False,
) -> dict:
    """Create a manual account via POST /accounts/.

    account_type: CHECKING, SAVINGS, INVESTMENT, or CREDITCARD (UK current account = CHECKING).
    balance is the opening balance. Pass either emoji or twitter_handle for the icon, not both.
    Requires confirm=true; confirm=false returns a preview. Does NOT move real bank money."""
    valid_types = {"CHECKING", "SAVINGS", "INVESTMENT", "CREDITCARD"}
    if account_type not in valid_types:
        return {"error": f"account_type must be one of {sorted(valid_types)}."}
    if emoji and twitter_handle:
        return {"error": "Provide either emoji or twitter_handle, not both."}
    body: dict = {"name": name, "type": account_type, "balance": balance, "currency": currency}
    if emoji:
        body["emoji"] = emoji
    if twitter_handle:
        body["iconProvider"] = "TWITTER"
        body["iconProviderHandle"] = twitter_handle
    if not confirm:
        return _preview("create_manual_account", "POST", "/accounts/", body=body)
    return {"status": "created", "result": api.post("/accounts/", body)}


@mcp.tool(annotations={"idempotentHint": True})
def update_manual_account(
    account_id: int,
    name: str | None = None,
    balance: float | None = None,
    emoji: str | None = None,
    twitter_handle: str | None = None,
    confirm: bool = False,
) -> dict:
    """Edit a MANUAL account via POST /accounts/{accountId}/edit.

    Allowed fields: name, balance, and icon (emoji or twitter_handle — not both).
    Fetches the account first and refuses unless provider is 'MANUAL'. Requires
    confirm=true; confirm=false returns a preview. Does NOT move real bank money
    — it only updates Emma's manual-account metadata."""
    account = api.sanitize_account_detail(api.get(f"/accounts/{account_id}"))
    if account.get("provider") != "MANUAL":
        return {
            "error": f"Account {account_id} is not manual (provider={account.get('provider')!r}). "
            "Only MANUAL accounts can be edited."
        }
    if emoji and twitter_handle:
        return {"error": "Provide either emoji or twitter_handle, not both."}
    changes: dict = {}
    if name is not None:
        changes["name"] = name
    if balance is not None:
        changes["balance"] = balance
    if emoji is not None:
        changes["emoji"] = emoji
    if twitter_handle is not None:
        changes["iconProvider"] = "TWITTER"
        changes["iconProviderHandle"] = twitter_handle
    if not changes:
        return {"error": "Provide at least one field to change (name, balance, emoji, twitter_handle)."}

    path = f"/accounts/{account_id}/edit"
    if not confirm:
        return _preview(
            "update_manual_account",
            "POST",
            path,
            body=changes,
            note=f"Target account '{account.get('name')}' is MANUAL.",
        )
    return {"status": "updated", "result": api.post(path, changes)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
