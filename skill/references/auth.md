# Amme API — full OAuth bootstrap

Only consult this when `scripts/auth.sh` reports refresh failure. For normal sessions, `auth.sh` reads `~/.config/amme/tokens.json`, refreshes if needed, and prints a bearer token — no manual flow required.

This 5-step flow runs once (first-time setup) or whenever the refresh token has been revoked. The result is a populated `~/.config/amme/tokens.json` containing `client_id`, `access_token`, and `refresh_token`.

`countryCode`, `phoneNumber`, and `pin` are expected as environment variables.

---

## Step 1 — get `clientId` and trigger SMS OTP

`POST /sign-in`

```json
{
  "phoneNumber": { "countryCode": "$countryCode", "phoneNumber": "$phoneNumber" }
}
```

Response: `{ clientId, nextStep: "sms_otp", ... }`. Remember `clientId`; the user receives an SMS OTP, which is `smsOtp` in the next step.

## Step 2 — submit SMS OTP

`POST /sign-in`

```json
{
  "clientId": "{{clientId}}",
  "phoneNumber": { "countryCode": "{{countryCode}}", "phoneNumber": "{{phoneNumber}}" },
  "smsOtp": "{{smsOtp}}",
  "sendSmsOtp": false
}
```

Response: `{ ..., nextStep: "pin" }`.

## Step 3 — submit PIN

`POST /sign-in`

```json
{
  "clientId": "{{clientId}}",
  "phoneNumber": { "countryCode": "{{countryCode}}", "phoneNumber": "{{phoneNumber}}" },
  "pin": "$pin",
  "sendSmsOtp": false,
  "smsOtp": "{{smsOtp}}"
}
```

Response: `{ ..., nextStep: "token" }`.

## Step 4 — exchange for OAuth tokens

`POST /oauth/token`

```json
{
  "clientId": "{{clientId}}",
  "client_id": "{{clientId}}",
  "grant_type": "multi_step",
  "phoneNumber": { "countryCode": "{{countryCode}}", "phoneNumber": "{{phoneNumber}}" },
  "pin": "$pin",
  "scope": "offline_access",
  "sendSmsOtp": false,
  "smsOtp": "{{smsOtp}}"
}
```

Response:

```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

## Step 5 — persist to the token store

Write `client_id`, `access_token`, and `refresh_token` to `~/.config/amme/tokens.json`:

```json
{
  "client_id": "...",
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

From this point on, `scripts/auth.sh` handles refresh automatically — no need to repeat steps 1–4 until the refresh token is revoked.

---

## Notes

- The OAuth endpoint is rate-limited (~10 requests / minute). Don't loop refresh or sign-in calls.
- `auth.sh` decodes the JWT `exp` claim and refreshes within 60s of expiry; force a refresh with `auth.sh --force`.
- Each step must complete successfully before moving on. The `nextStep` field in each response signals the expected next call.
