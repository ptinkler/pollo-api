#!/bin/bash
# Synology Task Scheduler boot script
# ─────────────────────────────────────────────────────────────────────
# Add this as a Triggered Task in Synology DSM:
#   Control Panel → Task Scheduler → Create → Triggered Task → User-defined script
#   Event: Boot-up
#   User: root
#   Task Settings → Run command:
#     bash /path/to/pollo-api/synology-boot.sh
#   (adjust path to wherever your compose project lives)
# ─────────────────────────────────────────────────────────────────────
# Uses docker compose up -d which respects depends_on ordering and
# healthcheck conditions — unlike Docker's raw restart policy.
# ─────────────────────────────────────────────────────────────────────

COMPOSE_DIR="/path/to/pollo-api"   # ← set to your actual project path

cd "$COMPOSE_DIR" || exit 1

# Read specific vars from .env (avoids bash parse errors on complex values)
_env_get() { grep -m1 "^${1}=" "$COMPOSE_DIR/.env" 2>/dev/null | cut -d= -f2-; }

APP_HOSTNAME=$(_env_get APP_HOSTNAME)
COMPOSE_PROFILES=$(_env_get COMPOSE_PROFILES)
echo "Boot mode: COMPOSE_PROFILES=${COMPOSE_PROFILES:-novpn}"

# ── Install HTTP→HTTPS redirect into DSM's nginx ────────────────────
# DSM's reverse proxy can only proxy, not redirect. This injects a
# custom server block into DSM's nginx that catches plain HTTP requests
# for our hostname and 301-redirects them to HTTPS.
#
# IMPORTANT: Delete any HTTP (port 80) reverse proxy rule in DSM for
# this hostname — only keep the HTTPS (port 443) rule.
# ─────────────────────────────────────────────────────────────────────
REDIRECT_CONF="/etc/nginx/conf.d/http.pollo-http-redirect.conf"
HOSTNAME="${APP_HOSTNAME:?APP_HOSTNAME not set — add APP_HOSTNAME=your-hostname.local to .env}"  # from .env

DESIRED_CONF=$(cat <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${HOSTNAME};
    return 301 https://\$host\$request_uri;
}
EOF
)

if ! printf '%s\n' "$DESIRED_CONF" | cmp -s "$REDIRECT_CONF" - 2>/dev/null; then
    printf '%s\n' "$DESIRED_CONF" > "$REDIRECT_CONF"
    nginx -s reload 2>/dev/null || synow3tool --gen-all 2>/dev/null
    echo "Installed HTTPS redirect for ${HOSTNAME}"
else
    echo "HTTPS redirect for ${HOSTNAME} already in place"
fi

# Wait for Docker daemon to be fully ready
sleep 10

# Stop any half-started containers from Docker's restart policy
docker compose -p pollo-api down 2>/dev/null

# Bring everything up in the correct order (respects depends_on + healthchecks)
docker compose -p pollo-api up -d
