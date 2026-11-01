#!/usr/bin/env bash
# Apply the workshop settings to a TLJH hub with tljh-config.
#
# Settings come from environment variables (defaults in brackets):
#
#   WORKSHOP_PASSWORD [kept/generated]  The one password attendees share
#                           (8+ characters, not all digits). Attendees type any
#                           username they like plus this password. Saved in
#                           /root/workshop-password.txt; generated if unset.
#   ADMIN_PASSWORD [kept/generated]  Separate password for the admin user(s)
#                           (32+ characters). Saved in /root/admin-password.txt.
#   MEM_LIMIT      [4G]     RAM cap per attendee (kernels are restarted above it).
#   CPU_LIMIT      [2]      CPU cap per attendee (whole cores).
#   CULL_TIMEOUT   [7200]   Stop servers idle this many seconds (2 h, so a
#                           lunch break doesn't kill anyone's kernel).
#   HTTPS_DOMAIN   []       e.g. aeo-hub.myproject.cloud.edu.au. With
#   HTTPS_EMAIL    []       HTTPS_EMAIL set too, turns on Let's Encrypt.
#                           The DNS record must already point at this VM.
#
#   sudo WORKSHOP_PASSWORD=drone-day-2026 bash hub/configure.sh
#   sudo HTTPS_DOMAIN=aeo-hub.myproject.cloud.edu.au HTTPS_EMAIL=me@utas.edu.au bash hub/configure.sh
#
# Safe to re-run; each run sets the same values again.
set -euo pipefail

MEM_LIMIT="${MEM_LIMIT:-4G}"
CPU_LIMIT="${CPU_LIMIT:-2}"
CULL_TIMEOUT="${CULL_TIMEOUT:-7200}"
HTTPS_DOMAIN="${HTTPS_DOMAIN:-}"
HTTPS_EMAIL="${HTTPS_EMAIL:-}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this as root: sudo bash $0" >&2
    exit 1
fi
command -v tljh-config >/dev/null || { echo "tljh-config not found. Install TLJH first." >&2; exit 1; }
export HOME="${HOME:-/root}"
cfg() { tljh-config "$@" >/dev/null; }

# Use the value passed in, else the one saved by an earlier run, else a new
# random one. Saved root-only so you can read it back with sudo cat.
password() {  # password <file> <value> <length>
    local file=$1 value=$2
    if [ -z "$value" ] && [ -s "$file" ]; then value=$(cat "$file"); fi
    if [ -z "$value" ]; then
        value=$(python3 -c "import secrets; print(''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range($3)))")
    fi
    (umask 077; printf '%s\n' "$value" > "$file")
    printf '%s' "$value"
}
WORKSHOP_PASSWORD=$(password /root/workshop-password.txt "${WORKSHOP_PASSWORD:-}" 12)
ADMIN_PASSWORD=$(password /root/admin-password.txt "${ADMIN_PASSWORD:-}" 40)
case "$WORKSHOP_PASSWORD" in *[!0-9]*) ;; *) echo "WORKSHOP_PASSWORD must not be all digits" >&2; exit 1 ;; esac
[ ${#WORKSHOP_PASSWORD} -ge 8 ] || { echo "WORKSHOP_PASSWORD needs 8+ characters" >&2; exit 1; }
[ ${#ADMIN_PASSWORD} -ge 32 ] || { echo "ADMIN_PASSWORD needs 32+ characters" >&2; exit 1; }

# SharedPasswordAuthenticator is built into JupyterHub 5.3+
/opt/tljh/hub/bin/python -m pip install --quiet "jupyterhub>=5.3,<6"

echo "== Login: one shared workshop password, attendees choose their own username"
cfg set auth.type jupyterhub.authenticators.shared.SharedPasswordAuthenticator
cfg set auth.SharedPasswordAuthenticator.user_password "$WORKSHOP_PASSWORD"
# Admins (users.admin) must log in with this one instead
cfg set auth.SharedPasswordAuthenticator.admin_password "$ADMIN_PASSWORD"
# Any username is accepted (JupyterHub 5 otherwise lets nobody in)
cfg set auth.SharedPasswordAuthenticator.allow_all true
echo "   workshop password: sudo cat /root/workshop-password.txt"
echo "   admin password:    sudo cat /root/admin-password.txt"

echo "== Limits: ${MEM_LIMIT} RAM, ${CPU_LIMIT} CPU per attendee"
cfg set limits.memory "$MEM_LIMIT"
cfg set limits.cpu "$CPU_LIMIT"

echo "== Open JupyterLab (/lab) by default"
cfg set user_environment.default_app jupyterlab

echo "== Hide the hub setup files from attendees' file browser"
# nbgitpuller copies the whole repo into each home folder. These names are left
# out of listings (anywhere, not only the repo folder) but can still be opened
# by path. The first line repeats Jupyter Server's defaults, which this replaces.
hide_dir=/opt/tljh/user/etc/jupyter/jupyter_server_config.d
mkdir -p "$hide_dir"
cat > "$hide_dir/aeo-hide.json" <<'EOF'
{
  "ContentsManager": {
    "hide_globs": [
      "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "*.so", "*.dylib", "*~",
      "hub", "pixi.toml", "pixi.lock", "environment.yml", "requirements.txt"
    ]
  }
}
EOF

echo "== Idle culler: stop servers idle for ${CULL_TIMEOUT}s"
cfg set services.cull.enabled true
cfg set services.cull.timeout "$CULL_TIMEOUT"
cfg set services.cull.every 300

if [ -n "$HTTPS_DOMAIN" ] && [ -f /etc/caddy/Caddyfile ]; then
    echo "Caddy handles HTTPS on this hub (hub/setup-caddy.sh); leave HTTPS_DOMAIN unset." >&2
    exit 1
fi
if [ -n "$HTTPS_DOMAIN" ] && [ -n "$HTTPS_EMAIL" ]; then
    echo "== HTTPS via Let's Encrypt for $HTTPS_DOMAIN"
    if ! getent hosts "$HTTPS_DOMAIN" >/dev/null; then
        echo "   $HTTPS_DOMAIN does not resolve yet. Create the DNS record first." >&2
        exit 1
    fi
    echo "   $HTTPS_DOMAIN -> $(getent hosts "$HTTPS_DOMAIN" | awk '{print $1}')   (this VM: $(hostname -I))"
    cfg set https.enabled true
    cfg set https.letsencrypt.email "$HTTPS_EMAIL"
    tljh-config unset https.letsencrypt.domains >/dev/null 2>&1 || true
    cfg add-item https.letsencrypt.domains "$HTTPS_DOMAIN"
fi

echo "== Reloading the hub"
tljh-config reload
if [ -n "$HTTPS_DOMAIN" ] && [ -n "$HTTPS_EMAIL" ]; then
    tljh-config reload proxy
    echo "   Certificate is requested in the background; try https://$HTTPS_DOMAIN in a minute."
fi
echo "Done. Current settings: sudo tljh-config show"
