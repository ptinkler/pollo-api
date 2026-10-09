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
- Cookie-based authentication (HttpOnly session cookie)

## Quick Start

```bash
cp .env.example .env
# Edit .env — set POLLO_API_KEY, API_KEY, POLLO_HOST_DATA_DIR, PUID/PGID at minimum
docker compose up -d
```

Open `http://localhost:<APP_PORT>` (default `8080`).

On first load, enter your `API_KEY` in the prompt. It is stored as an HttpOnly session cookie.

## Configuration

All configuration is via `.env`. See `.env.example` for the full list.

| Variable | Description |
|----------|-------------|
| `POLLO_API_KEY` | Your Pollo API key |
| `API_KEY` | Key to protect this app's endpoints (leave unset to disable auth) |
| `POLLO_HOST_DATA_DIR` | Host path for persistent data (videos, DB) |
| `APP_PORT` | Host port to expose the app on (default `8080`) |
| `COMPOSE_PROFILES` | `novpn` (default) or `vpn` — selects the stack |
| `PUID` / `PGID` | User/group the app container runs as (run `id` to find values) |
| `APP_HOSTNAME` | Hostname for HTTPS redirect (Synology boot script) |
| `GLUETUN_API_KEY` | Gluetun control server API key (VPN stack only) |
| `HTTP_CONTROL_SERVER_AUTH_DEFAULT_ROLE` | Gluetun auth JSON (see `.env.example`) |

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

Designed for private/local network use. Authentication uses an HttpOnly `SameSite=Strict` session cookie — the API key is never stored in browser JS. Disable auth only on a trusted network (`API_KEY` unset).

## License

MIT — see [LICENSE](LICENSE).
