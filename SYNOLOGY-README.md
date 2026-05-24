Synology NAS setup
===================

This document explains how to run the pollo-api project on a Synology NAS (DSM). It covers prerequisites, recommended paths and permissions, how to start the compose project (so the required network/device capabilities are preserved), and how to make the stack start automatically on boot using the included `synology-boot.sh` helper.

Prerequisites
-------------
- A Synology NAS running DSM 7.x (instructions assume DSM 7, adapt where needed).
- Docker package installed (and the Docker "compose" CLI or plugin available). If your NAS does not provide `docker compose`, you can run the compose v2 plugin or use Portainer to manage stacks.
- SSH access enabled (Control Panel → Terminal & SNMP → Enable SSH) so you can run `docker compose` from the shell. Many advanced options used here (device mapping, capabilities, network_mode) are not fully supported via DSM's GUI.
- Sufficient privileges. You will create a scheduled task that runs as root (the `synology-boot.sh` requires root to modify system nginx and run docker compose).

High-level notes about this project
-----------------------------------
- The compose stack relies on a VPN/proxy container (`gluetun`) that requires NET_ADMIN capabilities and access to `/dev/net/tun`. To ensure the stack can create the virtual tun device and apply network capabilities, start the stack from the Synology shell or use an automated boot script that runs at system start as root.
- The `app` container runs as the UID/GID set by `PUID` and `PGID` in your `.env` file. Set these to match the owner of your host data directory. Run `id` on the NAS shell to find your values.

Recommended install path
------------------------
Choose a directory on your NAS to hold the compose project. This README uses `/path/to/pollo-api` as a placeholder — replace it with whatever path you choose. Example layout:

- Project root: /path/to/pollo-api
- Compose file: /path/to/pollo-api/docker-compose.yml
- Data dir (container mapping target): /path/to/pollo-api/data

Create project folder and copy files
-----------------------------------
1. SSH into your NAS as an admin user (or root if you prefer):

```bash
ssh admin@your-nas.local
sudo -i
```

2. Create directories and copy the repository contents into the chosen folder. Example (adjust to how you transfer the repository):

```bash
mkdir -p /path/to/pollo-api
cd /path/to/pollo-api
# copy the repo files here (scp, git clone, rsync, etc.)
```

3. Ensure the host data directory exists and set ownership to match the UID/GID you will put in `.env` as `PUID`/`PGID`:

```bash
mkdir -p /path/to/pollo-api/data
# Run `id` to find your UID and GID, then:
chown -R <PUID>:<PGID> /path/to/pollo-api/data
```

Environment variables
---------------------
Create a `.env` file in the compose folder (same directory as `docker-compose.yml`) and set at minimum the environment variables referenced by the compose file. Example `.env`:

```env
# App auth (leave unset to disable — not recommended)
API_KEY=your_strong_random_key_here

# Pollo API
POLLO_API_KEY=your_pollo_api_key_here
POLLO_DATA_DIR=/data

# Host port the app is exposed on
APP_PORT=8080

# Hostname used for HTTPS redirect (see synology-boot.sh)
APP_HOSTNAME=your-hostname.local

# Container user (run `id` on your NAS shell)
PUID=1000
PGID=1000

# Host data path
POLLO_HOST_DATA_DIR=/path/to/pollo-api/data

# VPN (Gluetun)
VPN_SERVICE_PROVIDER=your_vpn_provider
VPN_TYPE=wireguard
WIREGUARD_PRIVATE_KEY=your_wireguard_key_here
WIREGUARD_ADDRESSES=10.x.x.x/16
SERVER_COUNTRIES=your_country
GLUETUN_API_KEY=your_gluetun_api_key_here
TZ=UTC
```

Copy `.env.example` as a starting point — it documents every variable.

Note: `POLLO_HOST_DATA_DIR` is used in the compose mapping; in the compose file it is mounted as `${POLLO_HOST_DATA_DIR}:/data`. Set this to the absolute host path you want to use before starting the stack via the shell. If you want to keep the project portable, you can export the environment variable before calling `docker compose`:

```bash
export POLLO_HOST_DATA_DIR=/path/to/pollo-api/data
docker compose up -d
```

Starting the stack manually (recommended for first run)
-----------------------------------------------------
Set `COMPOSE_PROFILES` in `.env` before starting:

- `COMPOSE_PROFILES=novpn` — direct, no VPN (default)
- `COMPOSE_PROFILES=vpn` — all traffic routed through gluetun

Then from the Synology shell in the project folder:

```bash
cd /path/to/pollo-api
docker compose pull
docker compose up -d
```

Important: The VPN profile requires `/dev/net/tun` and NET_ADMIN capability. Start from the shell as root — the DSM GUI may block these settings causing gluetun to fail.

Automating startup on boot (use `synology-boot.sh`)
-------------------------------------------------
The repository includes `synology-boot.sh` which is designed to be used with DSM's Task Scheduler. It performs three useful tasks:

- Installs an HTTP→HTTPS redirect into DSM's nginx for the project's hostname (so plain HTTP is redirected to HTTPS).
- Waits for the Docker daemon then stops any half-started containers belonging to project `pollo-api` that Docker's restart policy might have left in a broken state.
- Runs `docker compose up -d`, respecting `COMPOSE_PROFILES` from `.env` (`novpn` or `vpn`), to bring the stack up respecting `depends_on` and `healthcheck` ordering.

Before using the script:

1. Edit `COMPOSE_DIR` at the top of `synology-boot.sh` to point to your actual project path.
2. Set `APP_HOSTNAME` in `.env` — used for the HTTPS redirect.
3. Set `COMPOSE_PROFILES=vpn` in `.env` to use the VPN stack on boot, or `COMPOSE_PROFILES=novpn` for the default no-VPN stack.

Install the script into Task Scheduler:

1. Make the script executable:

```bash
chmod +x /path/to/pollo-api/synology-boot.sh
```

2. Open DSM → Control Panel → Task Scheduler → Create → Triggered Task → User-defined script

   - Event: Boot-up
   - User: root
   - Task Settings → Run command: bash /path/to/pollo-api/synology-boot.sh

3. Save the task. On next boot the script will run and start the compose stack in the correct order.

Networking and ports
--------------------
- The host port is configured via `APP_PORT` in `.env` (default `8080` if unset). The compose file maps `${APP_PORT}:80` on the host to the container's internal HTTP port.
- If using the VPN stack, `gluetun` provides the network for the whole stack (via `network_mode: "service:gluetun"`). Adjust firewall and router rules to allow external traffic to the mapped port if you want public access.

If you use a reverse proxy on DSM (Reverse Proxy or Application Portal), follow the note in `synology-boot.sh`: remove any HTTP (port 80) reverse proxy for the hostname and keep only the HTTPS (port 443) proxy entry — the boot script injects a redirect that will forward HTTP to HTTPS automatically.

Updating the stack
------------------
To update images and restart with latest:

```bash
cd /path/to/pollo-api
docker compose pull
docker compose up -d
```

Troubleshooting
---------------
- gluetun fails to start / cannot access /dev/net/tun
  - Confirm `/dev/net/tun` exists on the NAS. Many Synology kernels include tun; if not present you'll need to enable it or run on a model/kernel that supports tun devices.
  - Start the stack from the shell as root so Docker can map /dev/net/tun.

- App cannot read/write to host data directory
  - Confirm `PUID`/`PGID` in `.env` match the owner of the host data folder. Run `id` to get your values, `chown -R PUID:PGID /path/to/data` to fix ownership.

- Use `docker compose logs -f <service>` to tail logs for suspect services (e.g. `docker compose logs -f gluetun`).

Advanced options
----------------
- If you prefer a GUI approach, Portainer (installed on the NAS) can manage stacks and respects compose files. However, verify Portainer allows passing device mappings and capability flags needed by `gluetun`.
- If your NAS does not provide `docker compose`, you can install the compose plugin via the Docker project's instructions or run Compose V1 (less recommended). The `synology-boot.sh` uses `docker compose` (v2 style).

Security and best practices
---------------------------
- Keep your `.env` out of version control and protect API keys.
- Do not expose ports unnecessarily — use a reverse proxy + HTTPS where possible.
- Test restores and upgrades in a safe environment before using in production.

Useful commands
---------------

Start / stop / upgrade:

```bash
# Start
cd /path/to/pollo-api
docker compose up -d

# Stop
docker compose down

# Pull new images and restart
docker compose pull
docker compose up -d
```

See also
--------
- `synology-boot.sh` (included) — script to run at boot via Task Scheduler
- `docker-compose.yml` — single compose file; profile selected via `COMPOSE_PROFILES` in `.env`
