# Authentication

Canonical reference for how users sign in to the deployed app, how API requests
are authorized, and how to add users. Serverless (AWS) deployments only. Local
development runs without authentication.

## Overview

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| Identity | Amazon Cognito user pool | Stores users, enforces the password policy, runs hosted sign-in |
| Browser | React app with AWS Amplify | Starts the OAuth flow, holds tokens in memory, refreshes them |
| API | API Gateway HTTP API, JWT authorizer | Rejects `POST /chat` without a valid access token (HTTP 401) |
| Lambda | Chat handler | Runs only for authorized requests; does not re-check the token |

Sign-up is invite-only. Users cannot register themselves.

## Resources

Terraform creates these in `infrastructure/terraform/modules/api/main.tf`:

- **User pool** (`<name_prefix>-users`): email is the username. Passwords need at
  least 12 characters, with upper- and lower-case letters, digits and symbols.
  `admin_create_user_config.allow_admin_create_user_only = true` blocks
  self-registration. Email uses Cognito's default sender (`COGNITO_DEFAULT`).
- **Hosted sign-in domain**: `<name_prefix>-<region>-<account_id>.auth.<region>.amazoncognito.com`.
- **App client** (`<name_prefix>-client`): public client, no secret. Authorization
  code flow with PKCE, scopes `openid` and `email`. Access and ID tokens last 1
  hour, refresh tokens 30 days. Token revocation is enabled.
- **Callback and sign-out URL**: the CloudFront origin (`cors_allow_origin`).
- **JWT authorizer** on `POST /chat`: issuer is the user pool endpoint, audience
  is the app client ID. `GET /health` has no authorizer.

Terraform outputs `user_pool_id`, `user_pool_client_id`, and `cognito_domain`.
The frontend build reads them (see [Deployment](DEPLOYMENT.md)).

## Sign-in flow

1. The user opens the CloudFront URL and selects **Sign in**.
2. Amplify redirects the browser to the Cognito hosted sign-in page using the
   authorization code flow with PKCE.
3. The user signs in. Cognito redirects back to the CloudFront origin with an
   authorization code, and Amplify exchanges it for tokens.
4. The app keeps the access token in memory. Amplify keeps the refresh token in
   memory too (`sharedInMemoryStorage`), so nothing is written to local storage.
5. Each API call sends `Authorization: Bearer <access token>`. API Gateway checks
   the signature, issuer, expiry and client ID before invoking the Lambda.

### Token handling in the frontend

Implemented in `chatbots/react-chatbot/src/auth/`:

- `authFetch.js` attaches the bearer token. On a `401`, it forces one refresh
  and retries once. If the refresh fails, it redirects to sign-in.
- `cognito.js` configures Amplify and performs the refresh and redirect calls.
- `tokenStore.js` holds the access token in a module variable.

A page reload clears the in-memory tokens. The next request then starts a new
sign-in. If the Cognito hosted session is still active, the redirect can complete
without a password prompt.

## Auth mode selection

Auth turns on only when all of these hold (`config/api.js`):

- `REACT_APP_API_URL` is set. This selects serverless mode. Without it, the build
  uses the local API and auth stays off, even if the Cognito variables are set.
- `REACT_APP_AUTH_ENABLED=true`, or both `REACT_APP_USER_POOL_ID` and
  `REACT_APP_USER_POOL_CLIENT_ID` are set.

Build-time variables:

| Variable | Value |
|----------|-------|
| `REACT_APP_API_URL` | API Gateway endpoint (`api_endpoint` output) |
| `REACT_APP_AUTH_ENABLED` | `true` |
| `REACT_APP_USER_POOL_ID` | `user_pool_id` output |
| `REACT_APP_USER_POOL_CLIENT_ID` | `user_pool_client_id` output |
| `REACT_APP_COGNITO_DOMAIN` | `cognito_domain` output |
| `REACT_APP_AWS_REGION` | The deployment region |

## Adding users

Administrators create users with the CLI. Cognito emails a temporary password.

Get the pool ID from the Terraform outputs of the environment you deployed:

```bash
cd infrastructure/terraform
terraform output -raw user_pool_id
```

Use the pool that Terraform created (`<name_prefix>-users`, for example
`strands-rag-dev-users` in `dev`). Do not add users to a pool created outside
Terraform.

Create the user. The pool signs users in by email, so `--username` is the email
address:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <user_pool_id> \
  --username user@example.com \
  --user-attributes Name=email,Value=user@example.com Name=email_verified,Value=true \
  --desired-delivery-mediums EMAIL
```

The user opens the app, selects **Sign in**, enters the temporary password, and
sets a permanent one. Cognito requires that password change on first sign-in.
Check the status at any time:

```bash
aws cognito-idp admin-get-user --user-pool-id <user_pool_id> --username user@example.com
```

`UserStatus` is `FORCE_CHANGE_PASSWORD` until the first sign-in, then `CONFIRMED`.

Other operations:

- **Resend the invitation**: add `--message-action RESEND` to the same command.
- **Remove a user**: `aws cognito-idp admin-delete-user --user-pool-id <user_pool_id> --username user@example.com`.
- **Reset a password**: `aws cognito-idp admin-set-user-password --user-pool-id <user_pool_id> --username user@example.com --password '<new>' --permanent`, or
  `admin-reset-user-password` to force a reset on next sign-in.
- **List users**: `aws cognito-idp list-users --user-pool-id <user_pool_id>`.

## Email delivery

Email uses Cognito's default sender. It needs no SES setup and sends from a
Cognito address. Cognito limits the daily send volume on this sender. Switch to
Amazon SES (`email_sending_account = "DEVELOPER"` with a verified SES identity)
before inviting many users.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `401 {"message":"Unauthorized"}` from `/chat` | Missing or expired token, or issuer and client ID do not match the Terraform outputs. Check `REACT_APP_USER_POOL_CLIENT_ID`. |
| `Missing Cognito configuration: ...` in the browser console | A `REACT_APP_USER_POOL_*` or `REACT_APP_COGNITO_DOMAIN` value was not set at build time. Rebuild with all values. |
| Hosted sign-in shows `redirect_mismatch` | The URL in the browser differs from `cors_allow_origin`. Update the variable and re-apply, or open the registered origin. |
| Invitation email never arrives | Check the spam folder and the address. The Cognito default sender has a daily cap. Resend with `--message-action RESEND`. |
| Sign-in page has no sign-up link | Expected. Invite-only sign-up hides self-registration. |
| Sign-in works locally but the app never asks for it | Local mode bypasses auth. Use a serverless build (`REACT_APP_API_URL` set to the API endpoint). |

## Local development

`api_server.py` and the local frontend build do not check tokens. The Cognito
pool and the JWT authorizer exist only in the deployed API Gateway. See
[SERVERLESS_LOCAL.md](SERVERLESS_LOCAL.md) for local serverless emulation,
which also runs without auth.
