# One9Founders Cloud (OpenWorker broker)

A from-scratch OpenWorker-compatible cloud sign-in + managed OAuth broker.

**Data stays on One9Founders** — not `api.openworker.com`. Chats, files, and model
keys still never leave the desktop; this service only handles:

1. Account sign-in (Google → One9 user + JWT)
2. Optional one-click connector OAuth (Google/Gmail first)
3. Content-free telemetry ack (optional)

## Endpoints

| Path | Role |
|------|------|
| `GET /cloud/` | Human landing + config snippet |
| `GET /openworker/` | Windows One9 worker download page |
| `GET /v1/openworker/releases` | JSON download URLs for one9founders.com |
| `GET /v1/openworker/download/windows` | Windows setup EXE (local file or S3 redirect) |
| `GET /authorize` | One9-branded sign-in page (Auth0-shaped) |
| `POST /oauth/token` | PKCE code → JWT (Auth0-shaped) |
| `GET /v1/auth/callback` | Bounce to `127.0.0.1:{port}/auth/callback` |
| `GET /v1/me` | Signed-in account |
| `GET /v1/connections` | Managed connection metadata |
| `POST /v1/connections/{id}/disconnect` | Disconnect + clear server tokens |
| `POST /v1/oauth/google/start` | Begin Gmail/Calendar/Drive one-click |
| `GET /v1/oauth/google/callback` | Form-POST tokens to OpenWorker sidecar |
| `POST /v1/oauth/google/refresh` | Refresh managed Google tokens |
| `POST /v1/telemetry/events` | Auth required; ack only (no content storage) |

Full architecture, QA, and launch checklist: [`OPENWORKER_ONE9_INTEGRATION.md`](./OPENWORKER_ONE9_INTEGRATION.md).

## Env

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
COWORKER_CLOUD_CLIENT_ID=one9founders-openworker-dev
COWORKER_CLOUD_PUBLIC_URL=http://127.0.0.1:8000   # or https://api.one9founders.com
COWORKER_CLOUD_AUDIENCE=http://127.0.0.1:8000
```

Register these Google OAuth redirect URIs:

- `{COWORKER_CLOUD_PUBLIC_URL}/oidc/google/callback` — account sign-in
- `{COWORKER_CLOUD_PUBLIC_URL}/v1/oauth/google/callback` — connector connect

## Point OpenWorker at One9

`~/.config/coworker/config.toml`:

```toml
cloud_base_url = "http://127.0.0.1:8000"
cloud_auth_domain = "127.0.0.1:8000"
cloud_client_id = "one9founders-openworker-dev"
cloud_audience = "http://127.0.0.1:8000"
```

Production:

```toml
cloud_base_url = "https://api.one9founders.com"
cloud_auth_domain = "api.one9founders.com"
cloud_client_id = "<prod client id>"
cloud_audience = "https://api.one9founders.com"
```

Restart `openworker-server` after editing config.

## Windows installer

```bash
# after packaging/build_windows.ps1
python manage.py publish_openworker_windows path/to/setup.exe
# local-only (no S3):  python manage.py publish_openworker_windows path/to/setup.exe --no-upload
```

Then open `/openworker/` or `GET /v1/openworker/download/windows`.

## Migrate + run

```bash
cd backend
python manage.py migrate coworker_cloud
python manage.py runserver 8000
# open http://127.0.0.1:8000/cloud/
```

## Status

- ✅ Account sign-in via Google (One9 page)
- ✅ Google managed OAuth for `gmail`, `google_calendar`, `google_drive`
- ⏳ Slack / GitHub / Notion / HubSpot one-click — same pattern, not wired yet
- Note: OpenWorker may still mark Gmail one-click `managed_paused` until Google
  verification clears on *their* app; your One9 Google Cloud project is separate.
