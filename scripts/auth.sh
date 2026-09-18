#!/usr/bin/env bash
# Print a valid Amme API bearer token to stdout.
#
# Reads ~/.config/amme/tokens.json, decodes the JWT exp claim, and refreshes
# via POST /oauth/token (grant_type=refresh_token) if the cached access_token
# is within 60s of expiry. New tokens are written back to the same file.
#
# Usage:
#   curl -H "Authorization: Bearer $(scripts/auth.sh)" "$BASE/me"
#   scripts/auth.sh --force      # refresh unconditionally
#
# On refresh failure (e.g. revoked refresh_token) the script exits non-zero
# and prints a pointer to references/auth.md for the full OAuth bootstrap.

set -euo pipefail

TOKENS_FILE="${AMME_TOKENS_FILE:-$HOME/.config/amme/tokens.json}"
API_BASE="${AMME_API_BASE:-https://api.emma-app.com}"
LEEWAY_SECONDS=60

err() { printf '%s\n' "$*" >&2; }

force=0
case "${1:-}" in
  --force|-f) force=1 ;;
  -h|--help)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  '') : ;;
  *) err "auth.sh: unknown arg: $1"; exit 2 ;;
esac

if [[ ! -f "$TOKENS_FILE" ]]; then
  err "auth.sh: tokens file not found at $TOKENS_FILE"
  err "auth.sh: run the OAuth bootstrap in references/auth.md to create it"
  exit 1
fi

for bin in jq curl base64; do
  command -v "$bin" >/dev/null 2>&1 || { err "auth.sh: missing dependency: $bin"; exit 1; }
done

# Returns 0 (true) if the JWT's exp is within LEEWAY_SECONDS of now, or
# unparseable; non-zero otherwise.
jwt_expiring() {
  local token=$1 payload exp now
  payload=$(printf '%s' "$token" | cut -d. -f2 | tr '_-' '/+')
  while (( ${#payload} % 4 )); do payload="${payload}="; done
  exp=$(printf '%s' "$payload" | base64 -d 2>/dev/null | jq -r '.exp // empty' 2>/dev/null || true)
  [[ -z "$exp" ]] && return 0
  now=$(date +%s)
  (( exp - now <= LEEWAY_SECONDS ))
}

refresh_tokens() {
  local client_id refresh_token resp new_access new_refresh tmp
  client_id=$(jq -r '.client_id // empty' "$TOKENS_FILE")
  refresh_token=$(jq -r '.refresh_token // empty' "$TOKENS_FILE")
  if [[ -z "$client_id" || -z "$refresh_token" ]]; then
    err "auth.sh: tokens.json missing client_id or refresh_token"
    err "auth.sh: see references/auth.md for full OAuth bootstrap"
    exit 1
  fi

  local body
  body=$(jq -n --arg cid "$client_id" --arg rt "$refresh_token" \
    '{grant_type:"refresh_token", client_id:$cid, refresh_token:$rt}')

  resp=$(curl -sS -X POST "$API_BASE/oauth/token" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json' \
    -H 'User-Agent: Emma/999 CFNetwork iOS' \
    -H 'Origin: https://web.emma-app.com' \
    -H 'Referer: https://web.emma-app.com/' \
    --data "$body") || {
      err "auth.sh: network error contacting $API_BASE/oauth/token"
      exit 1
    }

  new_access=$(printf '%s' "$resp" | jq -r '.access_token // empty' 2>/dev/null || true)
  new_refresh=$(printf '%s' "$resp" | jq -r '.refresh_token // empty' 2>/dev/null || true)

  if [[ -z "$new_access" || -z "$new_refresh" ]]; then
    err "auth.sh: refresh failed; response did not contain new tokens"
    err "auth.sh: re-bootstrap via references/auth.md"
    exit 1
  fi

  tmp=$(mktemp "${TOKENS_FILE}.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  jq --arg at "$new_access" --arg rt "$new_refresh" \
     '.access_token = $at | .refresh_token = $rt' \
     "$TOKENS_FILE" > "$tmp"
  mv "$tmp" "$TOKENS_FILE"
  chmod 600 "$TOKENS_FILE" 2>/dev/null || true
  trap - EXIT

  printf '%s\n' "$new_access"
}

access_token=$(jq -r '.access_token // empty' "$TOKENS_FILE")
if [[ -z "$access_token" ]]; then
  err "auth.sh: tokens.json missing access_token"
  exit 1
fi

if (( force )) || jwt_expiring "$access_token"; then
  refresh_tokens
else
  printf '%s\n' "$access_token"
fi
