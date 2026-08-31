import amme_client as api
from fastmcp import FastMCP

mcp = FastMCP(
    name="amme",
    instructions=(
        "Amme personal finance assistant. "
        "Create/delete operations only work on MANUAL accounts (provider='MANUAL'). "
        "For date-windowed spending analysis, prefer get_spending_by_category or get_spending_totals "
        "over fetching all transactions. "
        "Use list_categories to resolve category display names to id strings before filtering or "
        "updating transactions. "
        "A transaction's display name is customName if set, otherwise counterpartName. "
        "Transactions are returned in reverse-chronological order. "
        "Account type CHECKING is a UK current account — display it to users as 'Current account'. "
        "Destructive tools (delete_transaction, delete_account) require confirm=True."
    ),
)

# ---------------------------------------------------------------------------
# Feed & User
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_feed() -> dict:
    """Dashboard snapshot: net worth, this-month spending/income/committed, last 3 transactions, unread notification count."""
    return api.get("/feed")


@mcp.tool(annotations={"readOnlyHint": True})
def get_me(with_walkthrough: bool = False) -> dict:
    """Current user profile: id, email, name, currency, payday range, premium status.
    with_walkthrough=True includes the onboarding walkthrough object."""
    params = {"withWalkthrough": "true"} if with_walkthrough else None
    return api.get("/me", params=params)


@mcp.tool(annotations={"readOnlyHint": True})
def get_user_additional_info() -> dict:
    """KYC-style profile fields: credit rating, employment status, job title, employer,
    gross annual salary, income/net-worth brackets, marital status, dependants, funding source,
    financial goals. Wrapped in { userAdditionalInfo: {...} }. Most fields may be null if not filled in."""
    return api.get("/user-additional-info")


@mcp.tool(annotations={"readOnlyHint": True})
def get_notifications(page: int = 1, per_page: int = 20) -> dict:
    """In-app notification list: budget alerts, payments received, subscription charges, product updates."""
    return api.get("/notifications", params={"page": page, "perPage": per_page})


# ---------------------------------------------------------------------------
# Transactions — read
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def list_transactions(
    page: int = 1,
    per_page: int = 50,
    without_internal: bool = True,
    account_ids: list[int] | None = None,
) -> dict:
    """
    Full transaction list, newest first. No server-side date filter — use get_spending_by_category
    or get_spending_totals for date-windowed aggregates instead.
    without_internal=True excludes account-to-account transfers.
    """
    params: dict = {"page": page, "perPage": per_page, "withoutInternal": without_internal}
    if account_ids:
        params["accountIds[]"] = account_ids
    return api.get("/transactions", params=params)


@mcp.tool(annotations={"readOnlyHint": True})
def get_transaction(transaction_id: int) -> dict:
    """Full details for one transaction: category, merchant, labels, notes, pending status."""
    return api.get(f"/transactions/{transaction_id}")


@mcp.tool(annotations={"readOnlyHint": True})
def list_transactions_compact(page: int = 1, per_page: int = 100) -> dict:
    """
    Compact transaction list (~3× smaller) with bundled categories and merchants dictionaries.
    Prefer this for large history fetches when full transaction detail isn't needed.
    """
    return api.get("/transactions-compact", params={"page": page, "perPage": per_page})


# ---------------------------------------------------------------------------
# Transactions — write (manual accounts only)
# ---------------------------------------------------------------------------


@mcp.tool()
def create_transaction(
    account_id: int,
    amount: float,
    booking_date: str,
    category_id: str,
    custom_name: str,
    currency: str = "GBP",
    notes: str | None = None,
) -> dict:
    """
    Create a transaction on a MANUAL account. amount is negative for spending, positive for income.
    booking_date: ISO 8601, e.g. '2026-05-31T00:00:00+00:00'.
    category_id: use the id string (e.g. 'groceries'), not the display name — call list_categories to look up ids.
    userId is fetched automatically.
    POST response twist: customName comes back in counterpartName/realCounterpartName with customName: null — looks wrong, is normal.
    """
    user = api.get("/me")
    body: dict = {
        "accountId": account_id,
        "amount": amount,
        "bookingDate": booking_date,
        "categoryId": category_id,
        "currency": currency,
        "customName": custom_name,
        "updateAccountBalance": True,
        "userId": user["id"],
    }
    if notes is not None:
        body["notes"] = notes
    return api.post("/transactions/", body)


@mcp.tool(annotations={"idempotentHint": True})
def update_transactions(updates: list[dict]) -> dict:
    """
    Bulk-update one or more transactions. Each element must have 'id' plus changed fields:
    customName, categoryId, labels (list of strings), notes, amount, bookingDate, customDate.
    Pending transactions (isPending=true) cannot be updated.
    Example: [{"id": 12345, "categoryId": "groceries", "customName": "Tesco"}]
    """
    return api.patch("/transactions/", updates)


@mcp.tool(annotations={"destructiveHint": True})
def delete_transaction(transaction_id: int, confirm: bool = False) -> dict:
    """
    Delete a transaction from a MANUAL account. Irreversible — confirm must be True to proceed.
    Pending transactions (isPending=true) cannot be deleted.
    """
    if not confirm:
        return {"error": "Set confirm=True to delete this transaction."}
    return api.delete(f"/transactions/{transaction_id}")


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def list_bank_connections() -> dict:
    """All bank connections with nested accounts, balances, and sync status."""
    return api.get("/bank-connections")


@mcp.tool(annotations={"readOnlyHint": True})
def get_bank_connection(bank_connection_id: int) -> dict:
    """Single bank connection with live consent/sync state: needsReauth, consentExpiresAt, isSyncing."""
    return api.get(f"/bank-connections/{bank_connection_id}")


@mcp.tool(annotations={"readOnlyHint": True})
def get_account(account_id: int) -> dict:
    """Full details for one account: balance, type, IBAN, sort code, credit limit, sync timestamps."""
    return api.get(f"/accounts/{account_id}")


@mcp.tool()
def create_account(
    name: str,
    account_type: str,
    balance: float = 0.0,
    currency: str = "GBP",
    emoji: str | None = None,
    twitter_handle: str | None = None,
) -> dict:
    """
    Create a manual account. account_type: CHECKING, SAVINGS, INVESTMENT, CREDITCARD.
    UK current accounts use CHECKING. balance is the opening balance.
    Pass either emoji or twitter_handle for the icon, not both.
    """
    if emoji and twitter_handle:
        return {"error": "Provide either emoji or twitter_handle, not both."}
    body: dict = {"name": name, "type": account_type, "balance": balance, "currency": currency}
    if emoji:
        body["emoji"] = emoji
    if twitter_handle:
        body["iconProvider"] = "TWITTER"
        body["iconProviderHandle"] = twitter_handle
    return api.post("/accounts/", body)


@mcp.tool(annotations={"idempotentHint": True})
def edit_account(
    account_id: int,
    name: str | None = None,
    balance: float | None = None,
    currency: str | None = None,
    emoji: str | None = None,
) -> dict:
    """
    Update fields on a MANUAL account. Only pass the fields you want to change.
    """
    body = {k: v for k, v in {"name": name, "balance": balance, "currency": currency, "emoji": emoji}.items() if v is not None}
    return api.post(f"/accounts/{account_id}/edit", body)


@mcp.tool(annotations={"destructiveHint": True})
def delete_account(account_id: int, confirm: bool = False) -> dict:
    """
    Delete a MANUAL account and all its transactions. Irreversible — confirm must be True to proceed.
    """
    if not confirm:
        return {"error": "Set confirm=True to delete this account."}
    return api.delete(f"/accounts/{account_id}")


# ---------------------------------------------------------------------------
# Categories & Labels
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def list_categories() -> dict:
    """
    All spending categories with ids, display names, emoji, colors, and transaction counts.
    Always use the id field (e.g. 'groceries'), not displayName, when setting categoryId on transactions.
    """
    return api.get("/categories")


@mcp.tool(annotations={"readOnlyHint": True})
def list_labels() -> dict:
    """All labels (tags) in use with transaction counts and last-used dates."""
    return api.get("/labels")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_spending_by_category(date_from: str, date_to: str) -> dict:
    """
    Per-category spending totals for a date window. date_from/date_to: YYYY-MM-DD.
    Returns overall total, transactionsCount, spending, income, and a per-category breakdown.
    Prefer this over list_transactions for any date-windowed spending question.
    """
    return api.get("/analytics/categories", params={"dateFrom": date_from, "dateTo": date_to})


@mcp.tool(annotations={"readOnlyHint": True})
def get_spending_totals(
    date_from: str,
    date_to: str,
    step: str = "month",
    category_id: str | None = None,
) -> dict:
    """
    Bucketed spending/income totals over a date range.
    step: day, isoWeek, month, quarter, year, payperiod, custom.
    Monthly/quarterly/yearly/payperiod buckets include committed, committedIncome, daysLeft, isPayday fields.
    day and isoWeek steps omit those fields.
    Optionally filter to one category_id (income will be 0 when filtering by category).
    """
    params: dict = {"dateFrom": date_from, "dateTo": date_to, "step": step}
    if category_id:
        params["categoryId"] = category_id
    return api.get("/analytics/totals", params=params)


@mcp.tool(annotations={"readOnlyHint": True})
def list_merchants(date_from: str | None = None, date_to: str | None = None) -> dict:
    """
    Per-merchant spending aggregation. date_from/date_to: YYYY-MM-DD.
    Omit dates for all-time totals (can be a large response).
    Unknown counterparts are grouped under id=-1 'Unknown'.
    """
    params: dict = {}
    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to
    return api.get("/analytics/merchants", params=params or None)


@mcp.tool(annotations={"readOnlyHint": True})
def get_merchant_stats(merchant_id: int) -> dict:
    """Lifetime stats for one merchant: total spend, transaction count, average spend per transaction."""
    return api.get(f"/analytics/merchants/{merchant_id}")


@mcp.tool(annotations={"readOnlyHint": True})
def get_committed_spending(date_from: str, date_to: str) -> dict:
    """
    Predicted recurring subscription charges in a time window.
    date_from/date_to: full ISO 8601 datetime, e.g. '2026-05-01T00:00:00.000Z'.
    Returns total committed amount and each subscription with matching predicted charge dates.
    """
    return api.get("/analytics/committed", params={"from": date_from, "until": date_to})


# ---------------------------------------------------------------------------
# Balance history
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_balance_history(
    date_from: str,
    date_to: str,
    step: str = "1day",
    graph_section: str | None = None,
    account_ids: list[int] | None = None,
    account_types: list[str] | None = None,
) -> dict:
    """
    Balance time series. date_from/date_to: YYYY-MM-DD. step: 1day.
    Use exactly one filter: graph_section, account_ids, or account_types — not multiple.
    graph_section: NET_WORTH (default), EVERYDAY, SAVINGS, INVESTMENT.
    account_ids: combined balance across specific account ids.
    account_types: INVESTMENT, CRYPTO, CHECKING, SAVINGS, CREDITCARD.
    Results are newest-first.
    """
    params: dict = {"from": date_from, "to": date_to, "step": step}
    if graph_section:
        params["graphSection"] = graph_section
    if account_ids:
        params["accountIds[]"] = account_ids
    if account_types:
        params["accountTypes[]"] = account_types
    return api.get("/balance-history", params=params)


# ---------------------------------------------------------------------------
# Budgets, Subscriptions & Spaces
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def list_budgets() -> dict:
    """All budget categories with limits, current spend, and previous period averages."""
    return api.get("/budgets")


@mcp.tool(annotations={"readOnlyHint": True})
def list_subscriptions() -> dict:
    """Active and inactive subscriptions with merchant info, price, frequency, and charge predictions."""
    return api.get("/subscriptions")


@mcp.tool(annotations={"readOnlyHint": True})
def list_spaces() -> dict:
    """User spaces (financial compartments) with account counts and premium status."""
    return api.get("/spaces")


# ---------------------------------------------------------------------------
# Credit Score
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_credit_score_report() -> dict:
    """
    Full TransUnion credit report: personal information, and all credit accounts with
    balance history, limit history, payment status history, and account holder details.
    Feature-flagged — only available if credit_score flag is enabled for the user.
    Large response (~2.3MB uncompressed). reportDate shows when the report was last fetched.
    """
    return api.get("/credit-score/transunion/report")


@mcp.tool(annotations={"readOnlyHint": True})
def get_credit_score_history() -> dict:
    """
    TransUnion credit score history with contributing factors and next best action.
    Each history entry has: date, value (numeric score), factors (red/yellow/green arrays
    with id/type/message), nextBestAction, nextBestActionDisplayTitle.
    Red factors hurt the score, yellow are neutral/improving, green are positive.
    """
    return api.get("/credit-score/transunion/score/history")


# ---------------------------------------------------------------------------
# Data Breaches
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_data_breaches(page: int = 1, per_page: int = 20) -> dict:
    """
    Paged list of data breaches affecting monitored accounts.
    Each breach includes name, date, affected data types, and which monitored account was hit.
    """
    return api.get("/data-breaches", params={"page": page, "perPage": per_page})


@mcp.tool(annotations={"readOnlyHint": True})
def get_data_breaches_monitored_accounts() -> dict:
    """Email addresses currently being monitored for data breaches."""
    return api.get("/data-breaches/monitored-accounts")


# ---------------------------------------------------------------------------
# Automation Rules
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_automation_rules() -> dict:
    """
    Smart rules for auto-categorisation and transaction labelling.
    Each rule has match conditions (merchant, amount, keyword) and actions (category, label, custom name).
    Note: the trailing slash is significant — /automation-rules/ not /automation-rules.
    """
    return api.get("/automation-rules/")


# ---------------------------------------------------------------------------
# Feature Flags
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def get_feature_flags(flags: list[str]) -> dict:
    """
    Evaluate one or more feature flags for the current user.
    flags: list of flag name strings, e.g. ['credit_score', 'csv_imports', 'isa_transfer'].
    Returns { flags: { flag_name: bool|object, ... } }.
    Useful for checking whether a feature is enabled before attempting its endpoint.
    Known flags include: credit_score, credit_score_reports, credit_score_alerts,
    credit_score_history, csv_imports, auto_invest_v4, automated_savings_v2,
    isa_transfer, JISA, physical_assets, rent_reporting_two.
    """
    return api.get("/feature-flags/", params={"flags[]": flags})


if __name__ == "__main__":
    mcp.run(transport="stdio")
