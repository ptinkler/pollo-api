# Pollo API

A self-hosted web UI and API backend for generating videos via the [Pollo](https://pollo.ai) video generation API.

Originally built for rapid on-the-fly D&D resource creation — generating atmospheric video loops, character portraits, and scene backgrounds for tabletop use. Grew into a general-purpose personal Pollo frontend with project management, credit tracking, and VPN rotation.

## Features

- Generate videos from image + prompt via multiple Pollo models
- Project-based organisation with per-project galleries
- Credit usage tracking and balance display
- Source and reference image uploads (stored locally)
- Characters: a name, description and reference images, attachable to chats and generations so a character looks the same everywhere (made ad hoc in a chat, or saved and managed on the Characters page)
- VPN country rotation via Gluetun control API
- Background job polling with automatic recovery on restart
- Multi-user: email+password admin login plus OAuth (Google/Microsoft/X), per-user encrypted provider keys, per-user data isolation
- Cookie-based authentication (HttpOnly session cookie)

## Quick Start

```bash
cp .env.example .env
# Edit .env — set ADMIN_EMAILS, the three secrets, POLLO_HOST_DATA_DIR, PUID/PGID
docker compose up -d
```

Create the admin account from the CLI (it can't be done through the app):

```bash
docker compose exec app python -m web.provision_admin --email you@gmail.com --set-password
```

Then open `http://localhost:<APP_PORT>` (default `8080`) and sign in with that email + password (or an OAuth provider, if configured). Provider keys (Pollo, OpenRouter, Venice) are entered per-user in **Settings → Keys** and stored encrypted — never in `.env`.

Upgrading an existing single-user install? See [Users & access](#users--access) for the one ordering gotcha and `provision_admin`.

## Configuration

See `.env.example` for the full list.

| Variable | Description |
|----------|-------------|
| `ADMIN_EMAILS` | Comma-separated admin emails; they log in with a password and control the VPN |
| `ALLOWED_EMAILS` | Non-admins allowed to sign in via OAuth (admins always may) |
| `OPEN_SIGNUP` | `true` = anyone who authenticates gets an account |
| `SESSION_SECRET` | Signs the login cookie |
| `PASSWORD_PEPPER` | Server-side secret mixed into password hashes — set once, never change |
| `KEYS_SECRET` | Encrypts stored per-user provider keys — set once, never change |
| `PUBLIC_BASE_URL` | Public https base URL for OAuth callbacks (behind a proxy/DDNS) |
| `*_OAUTH_CLIENT_ID` / `*_OAUTH_CLIENT_SECRET` | Google/Microsoft/X credentials; a provider turns on when both are set |
| `POLLO_HOST_DATA_DIR` | Host path for persistent data (videos, DB) |
| `APP_PORT` | Host port to expose the app on (default `8080`) |
| `COMPOSE_PROFILES` | `novpn` (default) or `vpn` — selects the stack |
| `PUID` / `PGID` | User/group the app container runs as (run `id` to find values) |
| `APP_HOSTNAME` | Hostname for HTTPS redirect (Synology boot script) |
| `GLUETUN_API_KEY` | Gluetun control server API key (VPN stack only) |

Provider keys (`POLLO_API_KEY`, `OPENROUTER_API_KEY`, `VENICE_API_KEY`) are entered per-user in the UI and are never read from the environment.

## Users & access

Multi-user: each user signs in, gets their own data (chats, projects, media, characters, settings) and their own provider keys — no user sees another's. There is no API key; protection is by login session.

- **Sign-in** — admins (emails in `ADMIN_EMAILS`) use email + password; everyone else uses OAuth (Google/Microsoft/X). An OAuth login with an admin's email resolves to the same account.
- **Who gets in** — fail-closed. With none of `ADMIN_EMAILS`/`ALLOWED_EMAILS`/`OPEN_SIGNUP` set, only admins. `ALLOWED_EMAILS` admits a fixed list; `OPEN_SIGNUP=true` admits anyone who authenticates.
- **Admin accounts** — created only via the CLI, never through the app (so a visitor can't claim one):

  ```bash
  docker compose exec app python -m web.provision_admin --email you@gmail.com --set-password
  ```
- **Upgrading a single-user install** — set `ADMIN_EMAILS` **before the first start**: migration `0020` backfills all existing data to that admin (or to a throwaway `admin@local` if unset). Then run `provision_admin --email you@… --claim-orphans` to adopt any remaining unowned data and move the old shared library into the admin's folder.
- **OAuth setup** — set `PUBLIC_BASE_URL` and register each provider's redirect URI as `<PUBLIC_BASE_URL>/api/auth/callback/<provider>`.

## VPN Stack

Set `COMPOSE_PROFILES=vpn` in `.env` to route all outbound traffic through [Gluetun](https://github.com/qdm12/gluetun). Requires a WireGuard-compatible VPN provider.

```bash
# .env
COMPOSE_PROFILES=vpn
VPN_SERVICE_PROVIDER=your_vpn_provider
VPN_TYPE=wireguard
WIREGUARD_PRIVATE_KEY=...
WIREGUARD_ADDRESSES=...
```

## Models

| Model | Type | Notes |
|-------|------|-------|
| Pollo Dance 2.0 | img2vid | Full length/ratio control |
| Pollo Dance 2.0 Fast | img2vid | Faster variant |
| Pollo 2.0 | img2vid | 5s or 10s only |
| Pollo Dance Ref | ref2video | Multi-reference character/subject |
| Pollo Dance Ref Fast | ref2video | Faster variant |

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd web/frontend && npm install && cd -
make dev        # API on :5000, Vite dev server on :5173
make test       # pytest + vitest
make lint       # what CI checks
make format     # fix what can be fixed automatically
make hooks      # check (and fix) staged files on every commit
```

Code standards, enforced in CI:

- **Python** — [ruff](https://docs.astral.sh/ruff/) for linting (PEP 8, pyflakes, import order, bugbear,
  pyupgrade, simplifications, and a cyclomatic complexity limit of 10) and formatting. 120-column lines.
  Settings in `pyproject.toml`.
- **Frontend** — ESLint (`eslint:recommended` + `plugin:vue/recommended`, complexity limit 12) and Prettier
  (no semicolons, single quotes, 120 columns). Settings in `web/frontend/eslint.config.js` and `.prettierrc.json`.
- **Line endings** — LF everywhere (`.gitattributes`, `.editorconfig`).

## Data

All data (videos, source images, chat media, character images, SQLite DB) is stored in `POLLO_HOST_DATA_DIR` on the host. Back this up.

## NAS / Synology

See [SYNOLOGY-README.md](SYNOLOGY-README.md) for Synology DSM setup, boot automation, and HTTPS reverse proxy configuration.

## Security

Every endpoint requires a login session (an HttpOnly cookie holding a signed, expiring user id). Admin passwords are hashed with argon2id over an HMAC pepper (`PASSWORD_PEPPER`); access is fail-closed (see [Users & access](#users--access)); each user's data is isolated at the database layer; per-user provider keys are encrypted at rest (`KEYS_SECRET`). If you expose the app publicly, serve it over HTTPS and set `PUBLIC_BASE_URL`.

## License

MIT — see [LICENSE](LICENSE).
